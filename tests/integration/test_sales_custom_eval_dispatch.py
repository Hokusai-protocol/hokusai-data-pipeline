"""Integration coverage for sales BenchmarkSpec custom-eval dispatch."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pandas as pd
import pytest

from src.api.schemas.benchmark_spec import BenchmarkSpecResponse
from src.evaluation.custom_eval import run_custom_eval
from src.evaluation.scorers import resolve_scorer
from src.evaluation.tags import (
    DATASET_HASH_TAG,
    MLFLOW_NAME_TAG,
    PER_ROW_ARTIFACT_URI_TAG,
    PRIMARY_METRIC_TAG,
    SCORER_REF_TAG,
    STATUS_TAG,
)
from src.utils.metric_naming import derive_mlflow_name

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "schema" / "examples"
SPEC_ID = "d4c33f60-3cf4-4fc0-a0df-e7b166a2a3f2"
MODEL_ID = "sales-outreach-model-v3"
RUN_ID = "sales-custom-eval-run-001"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


class _PersistTempDir:
    """Context manager that pins parquet writes to a known tmp_path."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def __enter__(self) -> str:
        return str(self._path)

    def __exit__(self, *args: object) -> None:
        return None


class _FakeRun:
    def __init__(self, run_id: str = RUN_ID) -> None:
        self.info = SimpleNamespace(run_id=run_id)

    def __enter__(self) -> _FakeRun:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _FakeMlflow:
    """Tiny fake mlflow module that captures tags, metrics, and artifacts."""

    def __init__(self) -> None:
        # Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is handled externally.
        self.tags: dict[str, str] = {}
        self.metrics_logged: dict[str, float] = {}
        self.logged_artifacts: list[tuple[str, str]] = []

    def start_run(self, run_name: str | None = None, run_id: str | None = None) -> _FakeRun:
        return _FakeRun(run_id=run_id or RUN_ID)

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def log_metric(self, key: str, value: float) -> None:
        self.metrics_logged[key] = value

    def log_artifact(self, local_path: str, artifact_path: str = "") -> None:
        self.logged_artifacts.append((local_path, artifact_path))

    def evaluate(self, **kwargs: object) -> SimpleNamespace:
        raise AssertionError("mlflow.evaluate should not be used for direct sales scorer dispatch")


def _build_sales_benchmark_spec(dataset_path: Path, eval_spec: dict) -> dict:
    payload = {
        "spec_id": SPEC_ID,
        "model_id": MODEL_ID,
        "provider": "hokusai",
        "dataset_reference": str(dataset_path),
        "eval_split": "test",
        "target_column": "metric_name",
        "input_columns": [
            "row_id",
            "unit_id",
            "metric_name",
            "scorer_ref",
            "delivered_count",
            "revenue_amount_cents",
            "unsubscribe",
            "spam_complaint",
        ],
        "metric_name": eval_spec["primary_metric"]["name"],
        "metric_direction": eval_spec["primary_metric"]["direction"],
        "dataset_version": None,
        "eval_spec": eval_spec,
        "created_at": datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 7, 12, 30, tzinfo=UTC),
        "is_active": True,
    }
    return BenchmarkSpecResponse.model_validate(payload).model_dump(mode="json")


def _build_remote_sales_benchmark_spec(
    dataset_reference: str, dataset_version: str, eval_spec: dict
) -> dict:
    payload = {
        "spec_id": SPEC_ID,
        "model_id": MODEL_ID,
        "provider": "hokusai",
        "dataset_reference": dataset_reference,
        "eval_split": "test",
        "target_column": "metric_name",
        "input_columns": [
            "row_id",
            "unit_id",
            "metric_name",
            "scorer_ref",
            "delivered_count",
            "revenue_amount_cents",
            "unsubscribe",
            "spam_complaint",
        ],
        "metric_name": eval_spec["primary_metric"]["name"],
        "metric_direction": eval_spec["primary_metric"]["direction"],
        "dataset_version": dataset_version,
        "eval_spec": eval_spec,
        "created_at": datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 7, 12, 30, tzinfo=UTC),
        "is_active": True,
    }
    return BenchmarkSpecResponse.model_validate(payload).model_dump(mode="json")


def _metric_value_from_ref(rows: list[dict], scorer_ref: str) -> float:
    return float(resolve_scorer(scorer_ref).callable_(rows))


def test_sales_benchmark_spec_drives_canonical_metrics_and_artifact_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    eval_spec = _load_example("sales_eval_spec.exact_observed.v1.json")
    rows = [
        _load_example("sales_outcome_row.revenue.v1.json"),
        _load_example("sales_outcome_row.unsubscribe.v1.json"),
        _load_example("sales_outcome_row.spam_complaint.v1.json"),
    ]
    dataset_path = tmp_path / "sales_outcome_rows.json"
    dataset_path.write_text(json.dumps(rows), encoding="utf-8")

    benchmark_spec = _build_sales_benchmark_spec(dataset_path, eval_spec)

    primary_metric_name = eval_spec["primary_metric"]["name"]
    guardrail_specs = [g for g in eval_spec["guardrails"] if g.get("scorer_ref")]
    primary_mlflow_name = derive_mlflow_name(primary_metric_name)
    guardrail_mlflow_names = [derive_mlflow_name(spec["name"]) for spec in guardrail_specs]
    metric_values = {
        primary_mlflow_name: _metric_value_from_ref(
            rows, eval_spec["primary_metric"]["scorer_ref"]
        ),
        **{
            derive_mlflow_name(spec["name"]): _metric_value_from_ref(rows, spec["scorer_ref"])
            for spec in guardrail_specs
        },
    }
    fake_mlflow = _FakeMlflow()

    monkeypatch.setattr(
        "src.evaluation.custom_eval.tempfile.TemporaryDirectory",
        lambda: _PersistTempDir(tmp_path),
    )

    result = run_custom_eval(
        model_id=MODEL_ID,
        benchmark_spec=benchmark_spec,
        benchmark_spec_id=SPEC_ID,
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=None,
        seed=None,
        temperature=None,
    )

    expected_scorer_refs = sorted(
        {
            eval_spec["primary_metric"]["scorer_ref"],
            *(spec["scorer_ref"] for spec in eval_spec["guardrails"] if spec.get("scorer_ref")),
            *(
                spec["scorer_ref"]
                for spec in eval_spec.get("secondary_metrics", [])
                if spec.get("scorer_ref")
            ),
        }
    )
    parquet_path = tmp_path / "per_row.parquet"

    assert result["status"] == "success"
    assert result["benchmark_spec_id"] == SPEC_ID

    assert fake_mlflow.tags[PRIMARY_METRIC_TAG] == primary_metric_name
    assert fake_mlflow.tags[MLFLOW_NAME_TAG] == primary_mlflow_name
    assert fake_mlflow.tags[SCORER_REF_TAG] == ",".join(expected_scorer_refs)
    assert fake_mlflow.tags[STATUS_TAG] == "succeeded"

    assert primary_mlflow_name in fake_mlflow.metrics_logged
    assert fake_mlflow.metrics_logged[primary_mlflow_name] == pytest.approx(
        metric_values[primary_mlflow_name]
    )
    assert result["metrics"][primary_mlflow_name] == pytest.approx(
        metric_values[primary_mlflow_name]
    )

    unsubscribe_mlflow_name = derive_mlflow_name("sales:unsubscribe_rate")
    assert unsubscribe_mlflow_name in guardrail_mlflow_names
    assert fake_mlflow.metrics_logged[unsubscribe_mlflow_name] == pytest.approx(
        metric_values[unsubscribe_mlflow_name]
    )
    assert result["metrics"][unsubscribe_mlflow_name] == pytest.approx(
        metric_values[unsubscribe_mlflow_name]
    )

    for metric_name in [primary_mlflow_name, *guardrail_mlflow_names]:
        assert metric_name in result["metrics"]
        assert pd.notna(result["metrics"][metric_name])

    assert fake_mlflow.logged_artifacts == [(str(parquet_path), "eval_results")]
    assert (
        fake_mlflow.tags[PER_ROW_ARTIFACT_URI_TAG] == f"runs:/{RUN_ID}/eval_results/per_row.parquet"
    )

    written = pd.read_parquet(parquet_path)
    assert list(written["row_id"]) == [row["row_id"] for row in rows]
    assert list(written["unit_id"]) == [row["unit_id"] for row in rows]
    for metric_name in metric_values:
        assert metric_name in written.columns
    assert len(written) == len(rows)

    UUID(result["benchmark_spec_id"])


def test_sales_remote_benchmark_spec_uses_canonical_dataset_version_for_tags_and_dispatch() -> None:
    eval_spec = _load_example("sales_eval_spec.exact_observed.v1.json")
    dataset_version = "sha256:" + "d" * 64
    benchmark_spec = _build_remote_sales_benchmark_spec(
        "s3://bucket/sales/outcomes.json",
        dataset_version,
        eval_spec,
    )

    primary_metric_name = eval_spec["primary_metric"]["name"]
    primary_mlflow_name = derive_mlflow_name(primary_metric_name)
    rows = [
        _load_example("sales_outcome_row.revenue.v1.json"),
        _load_example("sales_outcome_row.unsubscribe.v1.json"),
    ]
    metric_values = {
        primary_mlflow_name: _metric_value_from_ref(
            rows, eval_spec["primary_metric"]["scorer_ref"]
        ),
    }
    fake_mlflow = _FakeMlflow(rows=rows, metric_values=metric_values)

    result = run_custom_eval(
        model_id=MODEL_ID,
        benchmark_spec=benchmark_spec,
        benchmark_spec_id=SPEC_ID,
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=None,
        seed=None,
        temperature=None,
    )

    assert result["status"] == "success"
    assert fake_mlflow.evaluate_kwargs is not None
    assert fake_mlflow.evaluate_kwargs["data"] == "s3://bucket/sales/outcomes.json"
    assert fake_mlflow.tags[DATASET_HASH_TAG] == dataset_version
