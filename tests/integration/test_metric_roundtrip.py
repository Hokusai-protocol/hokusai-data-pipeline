"""End-to-end round-trip tests: eval_spec → MLflow key → HEM → DeltaOne.

Auth-hook note: all MLflow interactions here use fake/mock clients that bypass
live Authorization headers and MLFLOW_TRACKING_TOKEN handling by design.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.api.schemas.benchmark_spec import EvalSpec
from src.evaluation.deltaone_evaluator import DeltaOneEvaluator
from src.evaluation.manifest import create_hem_from_mlflow_run

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

DATASET_HASH = "sha256:" + "a" * 64
CANONICAL_NAME = "workflow:success_rate_under_budget"
MLFLOW_KEY = "workflow_success_rate_under_budget"


def _make_mlflow_run(
    run_id: str,
    *,
    primary_tag: str = CANONICAL_NAME,
    metric_key: str = MLFLOW_KEY,
    metric_value: float = 0.85,
    n_samples: str = "10000",
) -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id, start_time=1_700_000_000_000, experiment_id="1"),
        data=SimpleNamespace(
            tags={
                "hokusai.model_id": "model-rt",
                "hokusai.eval_id": "eval-rt",
                "hokusai.primary_metric": primary_tag,
                "hokusai.dataset.id": "dataset-rt",
                "hokusai.dataset.hash": DATASET_HASH,
                "hokusai.dataset.num_samples": n_samples,
            },
            params={},
            metrics={metric_key: metric_value},
        ),
    )


class _FakeMlflowClient:
    def __init__(self, runs: dict[str, SimpleNamespace]) -> None:
        self._runs = runs
        self.tags_set: dict[str, dict[str, str]] = {}

    def get_run(self, run_id: str) -> SimpleNamespace:
        return self._runs[run_id]

    def search_runs(self, **_kwargs: object) -> list:
        return []

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        self.tags_set.setdefault(run_id, {})[key] = value


# ---------------------------------------------------------------------------
# Test 1: Pydantic schema auto-populates mlflow_name
# ---------------------------------------------------------------------------


def test_eval_spec_auto_populates_mlflow_name() -> None:
    es = EvalSpec(
        primary_metric={"name": CANONICAL_NAME, "direction": "higher_is_better"},
    )
    assert es.primary_metric.mlflow_name == MLFLOW_KEY


# ---------------------------------------------------------------------------
# Test 2: MetricLogger calls mlflow.log_metric with normalized key
# ---------------------------------------------------------------------------


def test_metric_logger_uses_normalized_key() -> None:
    from src.utils.metrics import MetricLogger

    mock_mlflow = MagicMock()
    with patch("src.utils.metrics.mlflow", mock_mlflow):
        logger = MetricLogger(allow_legacy_names=True)
        logger.log_metric(CANONICAL_NAME, 0.85)

    mock_mlflow.log_metric.assert_called_once_with(MLFLOW_KEY, 0.85)


# ---------------------------------------------------------------------------
# Test 3+4: create_hem_from_mlflow_run handles namespaced primary metric
# ---------------------------------------------------------------------------


def test_namespaced_primary_metric_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    run = _make_mlflow_run("run-rt")
    fake_mlflow = SimpleNamespace(get_run=lambda _id: run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-rt")

    assert manifest.primary_metric["name"] == CANONICAL_NAME
    assert manifest.primary_metric["mlflow_name"] == MLFLOW_KEY
    assert manifest.primary_metric["value"] == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# Test 5: DeltaOne resolves namespaced metric without raising
# ---------------------------------------------------------------------------


def test_deltaone_resolves_namespaced_metric() -> None:
    cand = _make_mlflow_run("cand", metric_value=0.87)
    base = _make_mlflow_run("base", metric_value=0.85)
    client = _FakeMlflowClient({"cand": cand, "base": base})

    class _Resolver:
        def get_active_spec_for_model(self, _model_id: str) -> dict:
            return {
                "spec_id": "spec-rt",
                "dataset_version": DATASET_HASH,
                "metric_name": CANONICAL_NAME,
                "tiebreak_rules": {"min_examples": 1000},
                "input_schema": {},
                "eval_spec": {"primary_metric": {"mlflow_name": MLFLOW_KEY}},
            }

    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
        benchmark_spec_resolver=_Resolver(),
    )

    decision = evaluator.evaluate_for_model("model-rt", "cand", "base")
    assert decision.accepted is True


# ---------------------------------------------------------------------------
# Test 6: Legacy run without mlflow_name resolves via tier-2 normalized name
# ---------------------------------------------------------------------------


def test_legacy_run_without_mlflow_name_resolves_via_normalized_fallback() -> None:
    """HEM/spec lacks mlflow_name; DeltaOne resolves via tier-2 normalized key."""
    cand = _make_mlflow_run("cand-leg", metric_value=0.87)
    base = _make_mlflow_run("base-leg", metric_value=0.85)
    client = _FakeMlflowClient({"cand-leg": cand, "base-leg": base})

    class _Resolver:
        def get_active_spec_for_model(self, _model_id: str) -> dict:
            return {
                "spec_id": "spec-leg",
                "dataset_version": DATASET_HASH,
                "metric_name": CANONICAL_NAME,
                "tiebreak_rules": {"min_examples": 1000},
                "input_schema": {},
                # No eval_spec.primary_metric.mlflow_name — legacy path
            }

    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
        benchmark_spec_resolver=_Resolver(),
    )

    decision = evaluator.evaluate_for_model("model-rt", "cand-leg", "base-leg")
    assert decision.accepted is True
