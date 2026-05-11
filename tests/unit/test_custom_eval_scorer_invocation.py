"""Unit tests for direct deterministic scorer invocation in custom_eval."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from src.evaluation.custom_eval import run_custom_eval
from src.evaluation.scorers import resolve_scorer
from src.evaluation.tags import PER_ROW_ARTIFACT_URI_TAG
from src.utils.metric_naming import derive_mlflow_name


class _FakeRun:
    def __init__(self, run_id: str = "run-direct-001") -> None:
        self.info = SimpleNamespace(run_id=run_id)

    def __enter__(self) -> _FakeRun:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _FakeMlflow:
    def __init__(self) -> None:
        # Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is handled externally.
        self.tags: dict[str, str] = {}
        self.metrics_logged: dict[str, float] = {}
        self.logged_artifacts: list[tuple[str, str]] = []
        self.evaluate_calls = 0

    def start_run(self, run_name: str | None = None, run_id: str | None = None) -> _FakeRun:
        return _FakeRun(run_id=run_id or "run-direct-001")

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def log_metric(self, key: str, value: float) -> None:
        self.metrics_logged[key] = value

    def log_artifact(self, local_path: str, artifact_path: str = "") -> None:
        self.logged_artifacts.append((local_path, artifact_path))

    def evaluate(self, **kwargs: Any) -> Any:
        self.evaluate_calls += 1
        raise AssertionError(
            "mlflow.evaluate should not be called for direct deterministic scorers"
        )


class _PersistTempDir:
    def __init__(self, path: Path) -> None:
        self._path = path

    def __enter__(self) -> str:
        return str(self._path)

    def __exit__(self, *args: object) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolated_scorer_registry():
    from src.evaluation.scorers import registry as _reg

    snapshot = dict(_reg._REGISTRY)
    yield
    _reg._REGISTRY.clear()
    _reg._REGISTRY.update(snapshot)


def _sales_rows() -> list[dict[str, Any]]:
    return [
        {
            "row_id": "row-1",
            "unit_id": "unit-1",
            "schema_version": "sales_outcome_row/v1",
            "metric_name": "sales:revenue_per_1000_messages",
            "scorer_ref": "sales:revenue_per_1000_messages",
            "delivered_count": 10,
            "revenue_amount_cents": 5000,
            "unsubscribe": False,
            "spam_complaint": False,
        },
        {
            "row_id": "row-2",
            "unit_id": "unit-2",
            "schema_version": "sales_outcome_row/v1",
            "metric_name": "sales:revenue_per_1000_messages",
            "scorer_ref": "sales:revenue_per_1000_messages",
            "delivered_count": 5,
            "revenue_amount_cents": 2500,
            "unsubscribe": True,
            "spam_complaint": False,
        },
    ]


def _write_dataset(tmp_path: Path, rows: list[dict[str, Any]], suffix: str) -> Path:
    dataset_path = tmp_path / f"sales_rows{suffix}"
    if suffix == ".json":
        dataset_path.write_text(json.dumps(rows), encoding="utf-8")
    elif suffix == ".jsonl":
        dataset_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows),
            encoding="utf-8",
        )
    elif suffix == ".parquet":
        pd.DataFrame(rows).to_parquet(dataset_path, index=False)
    else:
        raise AssertionError(f"unsupported suffix {suffix}")
    return dataset_path


def _benchmark_spec(dataset_path: Path) -> dict[str, Any]:
    return {
        "spec_id": "spec-sales-001",
        "model_id": "sales-model",
        "is_active": True,
        "dataset_reference": str(dataset_path),
        "dataset_version": None,
        "dataset_id": "sales-dataset",
        "eval_split": "test",
        "metric_name": "Primary Sales Revenue",
        "metric_direction": "higher_is_better",
        "eval_spec": {
            "primary_metric": {
                "name": "Primary Sales Revenue",
                "direction": "higher_is_better",
                "scorer_ref": "sales:revenue_per_1000_messages",
            },
            "secondary_metrics": [
                {
                    "name": "Secondary: Unsubscribe Rate",
                    "direction": "lower_is_better",
                    "scorer_ref": "sales:unsubscribe_rate",
                }
            ],
            "guardrails": [
                {
                    "name": "Guardrail: Spam Complaint Rate",
                    "direction": "lower_is_better",
                    "threshold": 0.2,
                    "scorer_ref": "sales:spam_complaint_rate",
                }
            ],
            "measurement_policy": {"window": "exact_observed_output"},
        },
    }


@pytest.mark.parametrize("suffix", [".json", ".jsonl", ".parquet"])
def test_run_custom_eval_invokes_registered_sales_scorers_for_local_datasets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    rows = _sales_rows()
    dataset_path = _write_dataset(tmp_path, rows, suffix)
    benchmark_spec = _benchmark_spec(dataset_path)
    fake_mlflow = _FakeMlflow()

    call_counts = {
        "sales:revenue_per_1000_messages": 0,
        "sales:unsubscribe_rate": 0,
        "sales:spam_complaint_rate": 0,
    }

    from src.evaluation.scorers import registry as scorer_registry

    for scorer_ref in list(call_counts):
        registered = scorer_registry._REGISTRY[scorer_ref]
        original_callable = registered.callable_

        def _make_spy(ref: str, original: Any):
            def _spy(spy_rows: list[dict[str, Any]]) -> float:
                call_counts[ref] += 1
                assert spy_rows == rows
                return float(original(spy_rows))

            return _spy

        scorer_registry._REGISTRY[scorer_ref] = scorer_registry.RegisteredScorer(
            metadata=registered.metadata,
            callable_=_make_spy(scorer_ref, original_callable),
        )

    monkeypatch.setattr(
        "src.evaluation.custom_eval.tempfile.TemporaryDirectory",
        lambda: _PersistTempDir(tmp_path),
    )

    result = run_custom_eval(
        model_id="sales-model",
        benchmark_spec=benchmark_spec,
        benchmark_spec_id="spec-sales-001",
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=None,
        seed=None,
        temperature=None,
    )

    expected_metrics = {
        derive_mlflow_name("Primary Sales Revenue"): float(
            resolve_scorer("sales:revenue_per_1000_messages").callable_(rows)
        ),
        derive_mlflow_name("Secondary: Unsubscribe Rate"): float(
            resolve_scorer("sales:unsubscribe_rate").callable_(rows)
        ),
        derive_mlflow_name("Guardrail: Spam Complaint Rate"): float(
            resolve_scorer("sales:spam_complaint_rate").callable_(rows)
        ),
    }

    assert fake_mlflow.evaluate_calls == 0
    assert result["metrics"] == pytest.approx(expected_metrics)
    assert fake_mlflow.metrics_logged == pytest.approx(expected_metrics)
    assert call_counts == {
        "sales:revenue_per_1000_messages": 2,
        "sales:unsubscribe_rate": 2,
        "sales:spam_complaint_rate": 2,
    }

    parquet_path = tmp_path / "per_row.parquet"
    written = pd.read_parquet(parquet_path)
    for metric_name, metric_value in expected_metrics.items():
        assert metric_name in written.columns
        assert list(written[metric_name]) == [metric_value] * len(rows)
    assert fake_mlflow.logged_artifacts == [(str(parquet_path), "eval_results")]
    assert (
        fake_mlflow.tags[PER_ROW_ARTIFACT_URI_TAG]
        == "runs:/run-direct-001/eval_results/per_row.parquet"
    )


def test_run_custom_eval_direct_dispatch_with_guardrail_only_scorer_ref(
    tmp_path: Path,
) -> None:
    rows = _sales_rows()
    dataset_path = _write_dataset(tmp_path, rows, ".json")
    benchmark_spec = {
        "spec_id": "spec-sales-guardrail-only",
        "model_id": "sales-model",
        "is_active": True,
        "dataset_reference": str(dataset_path),
        "dataset_version": None,
        "dataset_id": "sales-dataset",
        "eval_split": "test",
        "metric_name": "accuracy",
        "metric_direction": "higher_is_better",
        "eval_spec": {
            "primary_metric": {
                "name": "accuracy",
                "direction": "higher_is_better",
                "scorer_ref": None,
            },
            "secondary_metrics": [],
            "guardrails": [
                {
                    "name": "Guardrail: Unsubscribe Rate",
                    "direction": "lower_is_better",
                    "threshold": 0.2,
                    "scorer_ref": "sales:unsubscribe_rate",
                }
            ],
        },
    }
    fake_mlflow = _FakeMlflow()

    result = run_custom_eval(
        model_id="sales-model",
        benchmark_spec=benchmark_spec,
        benchmark_spec_id="spec-sales-guardrail-only",
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=None,
        seed=None,
        temperature=None,
    )

    metric_name = derive_mlflow_name("Guardrail: Unsubscribe Rate")
    expected_value = float(resolve_scorer("sales:unsubscribe_rate").callable_(rows))

    assert fake_mlflow.evaluate_calls == 0
    assert result["metrics"] == pytest.approx({metric_name: expected_value})
    assert fake_mlflow.metrics_logged == pytest.approx({metric_name: expected_value})
