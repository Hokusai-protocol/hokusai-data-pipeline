"""Additional edge-case tests for DeltaOne evaluator coverage."""

from __future__ import annotations

# Auth-hook note: this suite uses in-memory/patched MLflow test doubles only.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
import builtins
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.evaluation.deltaone_evaluator as deltaone_module
from src.evaluation.deltaone_evaluator import (
    DeltaOneEvaluator,
    _load_mlflow,
    _load_mlflow_client_class,
)


def test_delta_one_constructor_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="cooldown_hours"):
        DeltaOneEvaluator(cooldown_hours=-1)
    with pytest.raises(ValueError, match="min_examples"):
        DeltaOneEvaluator(min_examples=0)
    with pytest.raises(ValueError, match="delta_threshold_pp"):
        DeltaOneEvaluator(delta_threshold_pp=-0.1)


def test_load_mlflow_helpers_raise_descriptive_error_when_dependency_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def _import(name, glb=None, lcl=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "mlflow" or name.startswith("mlflow."):
            raise ImportError("mlflow unavailable")
        return real_import(name, glb, lcl, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    with pytest.raises(ImportError, match="mlflow is required"):
        _load_mlflow()

    with pytest.raises(ImportError, match="mlflow is required"):
        _load_mlflow_client_class()


def test_extract_metrics_supports_single_metric_without_primary_tag(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    run = make_mlflow_run("candidate", metric_name="pass_rate", metric_value=0.9)
    run.data.tags.pop("hokusai.primary_metric")
    client = make_fake_deltaone_mlflow_client({"candidate": run})

    hem = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
    )._extract_metrics_from_run("candidate")

    assert hem.metric_name == "pass_rate"


def test_extract_metrics_rejects_unresolvable_primary_metric(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    run = make_mlflow_run("candidate", extra_metrics={"f1": 0.8})
    run.data.tags.pop("hokusai.primary_metric")
    client = make_fake_deltaone_mlflow_client({"candidate": run})

    with pytest.raises(ValueError, match="Unable to resolve primary metric"):
        DeltaOneEvaluator(
            mlflow_client=client,
            cooldown_hours=0,
        )._extract_metrics_from_run("candidate")


def test_extract_metrics_rejects_missing_or_invalid_sample_size(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    missing = make_mlflow_run("missing")
    missing.data.tags.pop("hokusai.dataset.num_samples")

    invalid = make_mlflow_run("invalid", n_examples="many")

    client = make_fake_deltaone_mlflow_client({"missing": missing, "invalid": invalid})
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0)

    with pytest.raises(ValueError, match="Missing sample size"):
        evaluator._extract_metrics_from_run("missing")

    with pytest.raises(ValueError, match="Invalid sample size"):
        evaluator._extract_metrics_from_run("invalid")


def test_extract_metrics_uses_current_time_when_start_time_missing(
    make_mlflow_run,
    make_fake_deltaone_mlflow_client,
) -> None:
    run = make_mlflow_run("candidate", start_time_ms=None)
    run.info.start_time = None
    client = make_fake_deltaone_mlflow_client({"candidate": run})

    hem = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
    )._extract_metrics_from_run("candidate")

    assert hem.timestamp.tzinfo is not None


def test_cooldown_ignores_current_run_missing_tag_and_invalid_timestamps(
    make_fake_deltaone_mlflow_client,
) -> None:
    now = datetime.now(timezone.utc)
    runs = [
        SimpleNamespace(info=SimpleNamespace(run_id="current"), data=SimpleNamespace(tags={})),
        SimpleNamespace(info=SimpleNamespace(run_id="a"), data=SimpleNamespace(tags={})),
        SimpleNamespace(
            info=SimpleNamespace(run_id="b"),
            data=SimpleNamespace(tags={"hokusai.deltaone.evaluated_at": "not-a-date"}),
        ),
    ]
    client = make_fake_deltaone_mlflow_client({}, search_runs_result=runs)
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=24)

    ok, blocked_until = evaluator._check_cooldown(
        model_id="model-a",
        dataset_hash="sha256:" + "a" * 64,
        experiment_id="1",
        now=now,
        current_run_id="current",
    )

    assert ok is True
    assert blocked_until is None


def test_parse_utc_handles_invalid_and_naive_inputs() -> None:
    assert DeltaOneEvaluator._parse_utc("not-a-date") is None

    parsed = DeltaOneEvaluator._parse_utc("2024-01-01T10:00:00")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc


def test_create_default_mlflow_client_uses_loader_when_class_not_preloaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FallbackClient:
        pass

    monkeypatch.setattr(deltaone_module, "MlflowClient", None)
    monkeypatch.setattr(deltaone_module, "_load_mlflow_client_class", lambda: _FallbackClient)

    evaluator = DeltaOneEvaluator(mlflow_client=None, cooldown_hours=0)

    assert isinstance(evaluator._client, _FallbackClient)


def test_detect_delta_one_rejects_missing_tag_and_missing_metric() -> None:
    latest = SimpleNamespace(version="2", run_id="run-latest", tags={})
    baseline = SimpleNamespace(
        version="1",
        run_id="run-baseline",
        tags={"benchmark_value": "0.8"},
    )

    class _Client:
        def search_model_versions(self, _filter: str):
            return [latest, baseline]

        def get_run(self, _run_id: str):
            return SimpleNamespace(data=SimpleNamespace(metrics={}))

    with patch("src.evaluation.deltaone_evaluator.MlflowClient", return_value=_Client()):
        assert deltaone_module.detect_delta_one("model-a") is False

    latest.tags = {"benchmark_metric": "accuracy"}
    baseline.tags = {"benchmark_metric": "accuracy", "benchmark_value": "0.8"}

    with patch("src.evaluation.deltaone_evaluator.MlflowClient", return_value=_Client()):
        assert deltaone_module.detect_delta_one("model-a") is False


def test_detect_delta_one_handles_no_improvement_and_unexpected_errors() -> None:
    latest = SimpleNamespace(
        version="2",
        run_id="run-latest",
        tags={"benchmark_metric": "accuracy"},
    )
    baseline = SimpleNamespace(
        version="1",
        run_id="run-baseline",
        tags={"benchmark_metric": "accuracy", "benchmark_value": "0.85"},
    )

    class _Client:
        def search_model_versions(self, _filter: str):
            return [latest, baseline]

        def get_run(self, _run_id: str):
            return SimpleNamespace(data=SimpleNamespace(metrics={"accuracy": 0.851}))

    with patch("src.evaluation.deltaone_evaluator.MlflowClient", return_value=_Client()):
        assert deltaone_module.detect_delta_one("model-a") is False

    with patch(
        "src.evaluation.deltaone_evaluator._get_sorted_model_versions",
        side_effect=RuntimeError("boom"),
    ):
        with patch("src.evaluation.deltaone_evaluator.MlflowClient", return_value=_Client()):
            assert deltaone_module.detect_delta_one("model-a") is False
