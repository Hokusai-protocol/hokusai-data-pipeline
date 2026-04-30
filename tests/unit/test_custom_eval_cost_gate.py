"""Unit tests for custom_eval cost gate logic."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.evaluation.custom_eval import (
    CostGateExceeded,
    project_cost,
    run_custom_eval,
)
from src.evaluation.schema import MetricFamily
from src.evaluation.scorers import Aggregation, register_scorer
from src.evaluation.spec_translation import RuntimeAdapterSpec, RuntimeMetricSpec
from src.evaluation.tags import (
    FAILURE_REASON_TAG,
    PROJECTED_COST_TAG,
    STATUS_TAG,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_genai_spec(scorer_ref: str = "quality_judge") -> RuntimeAdapterSpec:
    return RuntimeAdapterSpec(
        spec_id="spec-001",
        model_id="model-a",
        dataset_id="dataset-x",
        dataset_version="sha256:" + "a" * 64,
        eval_split="test",
        input_schema={},
        output_schema={},
        primary_metric=RuntimeMetricSpec(
            name="accuracy",
            direction="higher_is_better",
            scorer_ref=scorer_ref,
        ),
        measurement_policy={"per_call_cost_usd": 0.02},
    )


def _make_deterministic_spec() -> RuntimeAdapterSpec:
    return RuntimeAdapterSpec(
        spec_id="spec-001",
        model_id="model-a",
        dataset_id="dataset-x",
        dataset_version="sha256:" + "a" * 64,
        eval_split="test",
        input_schema={},
        output_schema={},
        primary_metric=RuntimeMetricSpec(
            name="accuracy",
            direction="higher_is_better",
            scorer_ref="pass_rate",
        ),
    )


def _make_benchmark_spec_with_policy(
    policy: dict | None = None,
    scorer_ref: str = "quality_judge",
) -> dict[str, Any]:
    return {
        "spec_id": "spec-001",
        "model_id": "model-a",
        "is_active": True,
        "dataset_reference": "s3://bucket/data.json",
        "dataset_version": "sha256:" + "a" * 64,
        "dataset_id": "dataset-x",
        "eval_split": "test",
        "metric_name": "accuracy",
        "metric_direction": "higher_is_better",
        "eval_spec": {
            "primary_metric": {
                "name": "accuracy",
                "direction": "higher_is_better",
                "scorer_ref": scorer_ref,
            },
            "secondary_metrics": [],
            "guardrails": [],
            "measurement_policy": policy,
        },
    }


class _FakeRun:
    def __init__(self, run_id: str = "run-gate-001") -> None:
        self.info = SimpleNamespace(run_id=run_id)

    def __enter__(self) -> _FakeRun:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


class _FakeMlflow:
    def __init__(self, metrics: dict | None = None) -> None:
        # Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is handled externally.
        self._metrics = metrics or {}
        self.tags: dict[str, str] = {}
        self.evaluate_called = False

    def start_run(self, run_name: str | None = None, run_id: str | None = None) -> _FakeRun:
        return _FakeRun()

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def log_metric(self, key: str, value: float) -> None:
        pass

    def evaluate(self, **kwargs: Any) -> Any:
        self.evaluate_called = True
        return SimpleNamespace(metrics=self._metrics)


@pytest.fixture(autouse=True)
def _isolated_scorer_registry():
    """Snapshot built-in registrations, restore after test."""
    from src.evaluation.scorers import registry as _reg

    snapshot = dict(_reg._REGISTRY)
    yield
    _reg._REGISTRY.clear()
    _reg._REGISTRY.update(snapshot)


@pytest.fixture
def _quality_scorer():
    def _scorer(values: list[float]) -> float:
        return 0.0

    register_scorer(
        "quality_judge",
        callable_=_scorer,
        version="1.0.0",
        input_schema={"type": "array"},
        output_metric_keys=("quality_judge",),
        metric_family=MetricFamily.QUALITY,
        aggregation=Aggregation.MEAN,
    )


# ---------------------------------------------------------------------------
# project_cost
# ---------------------------------------------------------------------------


def test_project_cost_genai_only(_quality_scorer) -> None:
    spec = _make_genai_spec()
    result = project_cost(spec, num_rows=100, cap_usd=10.0)
    assert result.num_rows == 100
    assert result.num_genai_scorers == 1
    assert result.per_call_estimate_usd == pytest.approx(0.02)
    assert result.projected_usd == pytest.approx(100 * 1 * 0.02)
    assert result.cap_usd == pytest.approx(10.0)


def test_project_cost_deterministic_skipped() -> None:
    spec = _make_deterministic_spec()
    result = project_cost(spec, num_rows=100, cap_usd=None)
    assert result.num_genai_scorers == 0
    assert result.projected_usd == 0.0


def test_project_cost_genai_prefix_ref() -> None:
    spec = RuntimeAdapterSpec(
        spec_id="spec-001",
        model_id="model-a",
        dataset_id="x",
        dataset_version="sha256:" + "a" * 64,
        eval_split="test",
        input_schema={},
        output_schema={},
        primary_metric=RuntimeMetricSpec(
            name="score",
            direction="higher_is_better",
            scorer_ref="genai:correctness",
        ),
        measurement_policy={"per_call_cost_usd": 0.05},
    )
    result = project_cost(spec, num_rows=10, cap_usd=5.0)
    assert result.num_genai_scorers == 1
    assert result.projected_usd == pytest.approx(10 * 1 * 0.05)


# ---------------------------------------------------------------------------
# cost_gate in run_custom_eval
# ---------------------------------------------------------------------------


def test_cost_gate_exceeds_cap_raises_with_failure_tags(_quality_scorer) -> None:
    spec = _make_benchmark_spec_with_policy(policy=None, scorer_ref="quality_judge")
    spec["dataset_version"] = "sha256:" + "a" * 64

    fake_mlflow = _FakeMlflow()

    with patch("src.evaluation.custom_eval._count_rows", return_value=1000):
        with pytest.raises(CostGateExceeded, match="exceeds cap"):
            run_custom_eval(
                model_id="model-a",
                benchmark_spec=spec,
                benchmark_spec_id="spec-001",
                mlflow_module=fake_mlflow,
                mlflow_client=None,
                cli_max_cost=0.50,  # 1000 rows × 1 judge × $0.01 = $10 > $0.50
                seed=None,
                temperature=None,
            )

    assert fake_mlflow.tags.get(STATUS_TAG) == "failed"
    assert fake_mlflow.tags.get(FAILURE_REASON_TAG) == "cost_gate_exceeded"
    assert PROJECTED_COST_TAG in fake_mlflow.tags
    assert fake_mlflow.evaluate_called is False


def test_cost_gate_uses_measurement_policy_cap_over_cli(_quality_scorer) -> None:
    """Spec cap of $1.0 should win over CLI --max-cost $100.0."""
    spec = _make_benchmark_spec_with_policy(
        policy={"max_cost_usd": 1.0, "per_call_cost_usd": 0.01},
        scorer_ref="quality_judge",
    )
    spec["dataset_version"] = "sha256:" + "a" * 64

    fake_mlflow = _FakeMlflow()

    with patch("src.evaluation.custom_eval._count_rows", return_value=1000):
        with pytest.raises(CostGateExceeded):
            run_custom_eval(
                model_id="model-a",
                benchmark_spec=spec,
                benchmark_spec_id="spec-001",
                mlflow_module=fake_mlflow,
                mlflow_client=None,
                cli_max_cost=100.0,  # should be ignored; spec cap of 1.0 wins
                seed=None,
                temperature=None,
            )

    assert fake_mlflow.tags.get(FAILURE_REASON_TAG) == "cost_gate_exceeded"


def test_cost_gate_uses_cli_when_spec_omits(_quality_scorer) -> None:
    """--max-cost enforced when spec has no cap."""
    spec = _make_benchmark_spec_with_policy(
        policy={"per_call_cost_usd": 0.01},
        scorer_ref="quality_judge",
    )
    spec["dataset_version"] = "sha256:" + "a" * 64

    fake_mlflow = _FakeMlflow()

    with patch("src.evaluation.custom_eval._count_rows", return_value=1000):
        with pytest.raises(CostGateExceeded):
            run_custom_eval(
                model_id="model-a",
                benchmark_spec=spec,
                benchmark_spec_id="spec-001",
                mlflow_module=fake_mlflow,
                mlflow_client=None,
                cli_max_cost=1.0,  # 1000 rows × $0.01 = $10 > $1.0
                seed=None,
                temperature=None,
            )


def test_cost_gate_per_call_estimate_falls_back_to_env(_quality_scorer, monkeypatch) -> None:
    monkeypatch.setenv("HOKUSAI_DEFAULT_JUDGE_COST_USD", "0.05")

    spec = _make_benchmark_spec_with_policy(policy=None, scorer_ref="quality_judge")
    spec["dataset_version"] = "sha256:" + "a" * 64

    fake_mlflow = _FakeMlflow()

    with patch("src.evaluation.custom_eval._count_rows", return_value=10):
        with pytest.raises(CostGateExceeded):
            run_custom_eval(
                model_id="model-a",
                benchmark_spec=spec,
                benchmark_spec_id="spec-001",
                mlflow_module=fake_mlflow,
                mlflow_client=None,
                cli_max_cost=0.10,  # 10 rows × $0.05 = $0.50 > $0.10
                seed=None,
                temperature=None,
            )


def test_cost_gate_skipped_when_no_cap(_quality_scorer) -> None:
    """No cap → gate skipped even for GenAI spec."""
    spec = _make_benchmark_spec_with_policy(policy={"per_call_cost_usd": 0.01})
    spec["dataset_version"] = "sha256:" + "a" * 64

    fake_mlflow = _FakeMlflow(metrics={"accuracy": 0.8})
    mock_result = SimpleNamespace(metrics={"accuracy": 0.8})

    with patch("src.evaluation.custom_eval._dispatch_genai", return_value=mock_result):
        result = run_custom_eval(
            model_id="model-a",
            benchmark_spec=spec,
            benchmark_spec_id="spec-001",
            mlflow_module=fake_mlflow,
            mlflow_client=None,
            cli_max_cost=None,  # no cap
            seed=None,
            temperature=None,
        )

    assert result["status"] == "success"
    assert PROJECTED_COST_TAG not in fake_mlflow.tags


def test_cost_gate_skipped_for_deterministic_even_with_cap() -> None:
    """Deterministic-only spec with max_cost=0 → gate skipped."""
    spec = _make_benchmark_spec_with_policy(policy={"max_cost_usd": 0.0}, scorer_ref="pass_rate")
    spec["dataset_version"] = "sha256:" + "a" * 64

    fake_mlflow = _FakeMlflow(metrics={"accuracy": 0.8})

    result = run_custom_eval(
        model_id="model-a",
        benchmark_spec=spec,
        benchmark_spec_id="spec-001",
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=0.0,
        seed=None,
        temperature=None,
    )

    assert result["status"] == "success"
