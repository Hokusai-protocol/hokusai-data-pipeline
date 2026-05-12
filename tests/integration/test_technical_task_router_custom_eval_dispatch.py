"""Integration coverage for technical task router custom-eval dispatch."""

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
from src.evaluation.tags import (
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
SPEC_ID = "6d39cd7b-889b-4388-a779-f20b8d21c384"
MODEL_ID = "technical-task-router-challenger"
RUN_ID = "technical-task-router-custom-eval-run-001"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


class _PersistTempDir:
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
    def __init__(self) -> None:
        # Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is configured externally.
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
        raise AssertionError("mlflow.evaluate should not be used for task-router dispatch")


def _build_benchmark_spec(dataset_path: Path, eval_spec: dict) -> dict:
    payload = {
        "spec_id": SPEC_ID,
        "model_id": MODEL_ID,
        "provider": "hokusai",
        "dataset_reference": str(dataset_path),
        "eval_split": "test",
        "target_column": "completed_successfully",
        "input_columns": [
            "row_id",
            "task_descriptor",
            "allowed_models",
            "selected_models",
            "max_cost_usd",
            "actual_cost_usd",
        ],
        "metric_name": eval_spec["primary_metric"]["name"],
        "metric_direction": eval_spec["primary_metric"]["direction"],
        "dataset_version": None,
        "eval_spec": eval_spec,
        "task_type": "technical_task_router",
        "created_at": datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 12, 12, 30, tzinfo=UTC),
        "is_active": True,
    }
    return BenchmarkSpecResponse.model_validate(payload).model_dump(mode="json")


def test_task_router_benchmark_spec_scores_all_rows_and_persists_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    eval_spec = _load_example("technical_task_router_spec.v1.json")
    rows = [
        _load_example("technical_task_router_row.success.v1.json"),
        _load_example("technical_task_router_row.over_budget.v1.json"),
        _load_example("technical_task_router_row.disallowed_model.v1.json"),
        _load_example("technical_task_router_row.failed.v1.json"),
    ]
    dataset_path = tmp_path / "technical_task_router_rows.json"
    dataset_path.write_text(json.dumps(rows), encoding="utf-8")

    fake_mlflow = _FakeMlflow()
    monkeypatch.setattr(
        "src.evaluation.custom_eval.tempfile.TemporaryDirectory",
        lambda: _PersistTempDir(tmp_path),
    )

    result = run_custom_eval(
        model_id=MODEL_ID,
        benchmark_spec=_build_benchmark_spec(dataset_path, eval_spec),
        benchmark_spec_id=SPEC_ID,
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=None,
        seed=None,
        temperature=None,
    )

    primary_name = "technical_task_router.benchmark_score/v1"
    feasibility_name = "technical_task_router.feasibility/v1"
    primary_mlflow_name = derive_mlflow_name(primary_name)
    feasibility_mlflow_name = derive_mlflow_name(feasibility_name)
    parquet_path = tmp_path / "per_row.parquet"

    assert result["status"] == "success"
    assert result["benchmark_spec_id"] == SPEC_ID
    assert result["metrics"][primary_mlflow_name] == pytest.approx(0.25)
    assert result["metrics"][feasibility_mlflow_name] == pytest.approx(0.5)
    assert fake_mlflow.metrics_logged[primary_mlflow_name] == pytest.approx(0.25)
    assert fake_mlflow.metrics_logged[feasibility_mlflow_name] == pytest.approx(0.5)

    assert fake_mlflow.tags[PRIMARY_METRIC_TAG] == primary_name
    assert fake_mlflow.tags[MLFLOW_NAME_TAG] == primary_mlflow_name
    assert fake_mlflow.tags[SCORER_REF_TAG] == ",".join(
        sorted(
            {
                "technical_task_router.benchmark_score/v1",
                "technical_task_router.feasibility/v1",
            }
        )
    )
    assert fake_mlflow.tags[STATUS_TAG] == "succeeded"
    assert (
        fake_mlflow.tags[PER_ROW_ARTIFACT_URI_TAG] == f"runs:/{RUN_ID}/eval_results/per_row.parquet"
    )
    assert fake_mlflow.logged_artifacts == [(str(parquet_path), "eval_results")]

    written = pd.read_parquet(parquet_path)
    assert list(written["row_id"]) == [row["row_id"] for row in rows]
    assert primary_mlflow_name in written.columns
    assert feasibility_mlflow_name in written.columns
    assert len(written) == 4

    UUID(result["benchmark_spec_id"])
