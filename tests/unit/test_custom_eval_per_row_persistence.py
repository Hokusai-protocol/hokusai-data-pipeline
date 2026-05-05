"""Unit tests for per-row artifact persistence in custom_eval dispatch.

Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is handled by the injected
mlflow_module before custom_eval functions are called. Tests here use fake modules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from src.evaluation.custom_eval import _persist_per_row_artifact, _prepare_per_row_dataframe
from src.evaluation.schema import MetricFamily
from src.evaluation.scorers import Aggregation, register_scorer
from src.evaluation.spec_translation import RuntimeAdapterSpec, RuntimeMetricSpec
from src.evaluation.tags import PER_ROW_ARTIFACT_URI_TAG

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_spec(scorer_ref: str | None = "pass_rate") -> RuntimeAdapterSpec:
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
    )


@pytest.fixture(autouse=True)
def _isolated_scorer_registry():
    from src.evaluation.scorers import registry as _reg

    snapshot = dict(_reg._REGISTRY)
    yield
    _reg._REGISTRY.clear()
    _reg._REGISTRY.update(snapshot)


class _CapturingMlflow:
    """Fake mlflow module that captures log_artifact calls."""

    def __init__(self, raise_on_log_artifact: bool = False) -> None:
        self.logged_artifacts: list[tuple[str, str]] = []
        self.tags: dict[str, str] = {}
        self._raise_on_log_artifact = raise_on_log_artifact
        self.last_artifact_local_path: str | None = None

    def log_artifact(self, local_path: str, artifact_path: str = "") -> None:
        if self._raise_on_log_artifact:
            raise RuntimeError("simulated log_artifact failure")
        self.last_artifact_local_path = local_path
        self.logged_artifacts.append((local_path, artifact_path))

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value


def _make_result_df(n: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": [f"row-{i}" for i in range(n)],
            "accuracy": [bool(i % 2 == 0) for i in range(n)],
        }
    )


# ---------------------------------------------------------------------------
# _prepare_per_row_dataframe
# ---------------------------------------------------------------------------


def test_prepare_adds_row_id_when_missing() -> None:
    df = pd.DataFrame({"accuracy": [True, False, True]})
    spec = _make_spec()
    result = _prepare_per_row_dataframe(df, spec)
    assert "row_id" in result.columns
    assert list(result["row_id"]) == ["0", "1", "2"]


def test_prepare_casts_existing_row_id_to_str() -> None:
    df = pd.DataFrame({"row_id": [1, 2, 3], "accuracy": [True, False, True]})
    spec = _make_spec()
    result = _prepare_per_row_dataframe(df, spec)
    assert result["row_id"].dtype == object  # string dtype
    assert list(result["row_id"]) == ["1", "2", "3"]


def test_prepare_synthesizes_positional_ids_on_duplicates() -> None:
    df = pd.DataFrame({"row_id": ["a", "a", "b"], "accuracy": [True, False, True]})
    spec = _make_spec()
    result = _prepare_per_row_dataframe(df, spec)
    assert list(result["row_id"]) == ["0", "1", "2"]


def test_prepare_casts_unit_id_to_str() -> None:
    df = pd.DataFrame({"row_id": ["r1", "r2"], "unit_id": [10, 20], "accuracy": [True, False]})
    spec = _make_spec()
    result = _prepare_per_row_dataframe(df, spec)
    assert list(result["unit_id"]) == ["10", "20"]


def test_prepare_casts_outcome_metric_to_bool() -> None:
    def _scorer(values: list) -> float:
        return 0.0

    register_scorer(
        "bool_outcome_scorer",
        callable_=_scorer,
        version="1.0.0",
        input_schema={"type": "array"},
        output_metric_keys=("bool_outcome_scorer",),
        metric_family=MetricFamily.OUTCOME,
        aggregation=Aggregation.MEAN,
    )
    df = pd.DataFrame({"row_id": ["r1", "r2"], "bool_outcome_scorer": [1, 0]})
    spec = _make_spec(scorer_ref="bool_outcome_scorer")
    result = _prepare_per_row_dataframe(df, spec)
    assert result["bool_outcome_scorer"].dtype == bool


def test_prepare_does_not_mutate_original() -> None:
    df = pd.DataFrame({"accuracy": [True, False]})
    spec = _make_spec()
    result = _prepare_per_row_dataframe(df, spec)
    assert "row_id" not in df.columns
    assert "row_id" in result.columns


# ---------------------------------------------------------------------------
# _persist_per_row_artifact — success path
# ---------------------------------------------------------------------------


def test_persist_writes_parquet_and_sets_tag(tmp_path: Path) -> None:
    mlflow = _CapturingMlflow()
    result_df = _make_result_df(n=3)
    result = SimpleNamespace(result_df=result_df)
    spec = _make_spec()

    uri = _persist_per_row_artifact(
        mlflow_module=mlflow,
        result=result,
        runtime_spec=spec,
        run_id="run-abc123",
    )

    assert uri == "runs:/run-abc123/eval_results/per_row.parquet"
    assert len(mlflow.logged_artifacts) == 1
    assert mlflow.logged_artifacts[0][1] == "eval_results"
    assert mlflow.tags[PER_ROW_ARTIFACT_URI_TAG] == "runs:/run-abc123/eval_results/per_row.parquet"


def test_persist_uploaded_parquet_has_correct_row_count(tmp_path: Path) -> None:
    captured_paths: list[str] = []

    class _CapturingWithPath(_CapturingMlflow):
        def log_artifact(self, local_path: str, artifact_path: str = "") -> None:
            captured_paths.append(local_path)
            super().log_artifact(local_path, artifact_path)

    mlflow = _CapturingWithPath()
    result_df = _make_result_df(n=7)
    result = SimpleNamespace(result_df=result_df)
    spec = _make_spec()

    with patch(
        "src.evaluation.custom_eval.tempfile.TemporaryDirectory",
        return_value=_PersistTempDir(tmp_path),
    ):
        _persist_per_row_artifact(
            mlflow_module=mlflow,
            result=result,
            runtime_spec=spec,
            run_id="run-xyz",
        )

    assert len(captured_paths) == 1
    written = pd.read_parquet(captured_paths[0])
    assert len(written) == 7
    assert "row_id" in written.columns


class _PersistTempDir:
    """Context manager that uses a fixed tmp_path instead of a real temp dir."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def __enter__(self) -> str:
        return str(self._path)

    def __exit__(self, *args: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# _persist_per_row_artifact — no-op cases
# ---------------------------------------------------------------------------


def test_persist_returns_none_when_result_df_absent() -> None:
    mlflow = _CapturingMlflow()
    result = SimpleNamespace()  # no result_df attribute
    spec = _make_spec()
    uri = _persist_per_row_artifact(
        mlflow_module=mlflow,
        result=result,
        runtime_spec=spec,
        run_id="run-1",
    )
    assert uri is None
    assert not mlflow.logged_artifacts
    assert PER_ROW_ARTIFACT_URI_TAG not in mlflow.tags


def test_persist_returns_none_when_result_df_is_none() -> None:
    mlflow = _CapturingMlflow()
    result = SimpleNamespace(result_df=None)
    spec = _make_spec()
    uri = _persist_per_row_artifact(
        mlflow_module=mlflow,
        result=result,
        runtime_spec=spec,
        run_id="run-2",
    )
    assert uri is None


def test_persist_returns_none_when_result_df_empty() -> None:
    mlflow = _CapturingMlflow()
    result = SimpleNamespace(result_df=pd.DataFrame())
    spec = _make_spec()
    uri = _persist_per_row_artifact(
        mlflow_module=mlflow,
        result=result,
        runtime_spec=spec,
        run_id="run-3",
    )
    assert uri is None


def test_persist_returns_none_when_result_df_not_a_dataframe() -> None:
    mlflow = _CapturingMlflow()
    result = SimpleNamespace(result_df={"not": "a dataframe"})
    spec = _make_spec()
    uri = _persist_per_row_artifact(
        mlflow_module=mlflow,
        result=result,
        runtime_spec=spec,
        run_id="run-4",
    )
    assert uri is None


# ---------------------------------------------------------------------------
# _persist_per_row_artifact — failure isolation
# ---------------------------------------------------------------------------


def test_persist_does_not_raise_when_log_artifact_fails() -> None:
    mlflow = _CapturingMlflow(raise_on_log_artifact=True)
    result = SimpleNamespace(result_df=_make_result_df())
    spec = _make_spec()

    # Must not raise
    uri = _persist_per_row_artifact(
        mlflow_module=mlflow,
        result=result,
        runtime_spec=spec,
        run_id="run-5",
    )

    assert uri is None
    assert PER_ROW_ARTIFACT_URI_TAG not in mlflow.tags


def test_persist_does_not_set_tag_when_upload_fails() -> None:
    mlflow = _CapturingMlflow(raise_on_log_artifact=True)
    result = SimpleNamespace(result_df=_make_result_df())
    spec = _make_spec()

    _persist_per_row_artifact(
        mlflow_module=mlflow,
        result=result,
        runtime_spec=spec,
        run_id="run-6",
    )

    assert PER_ROW_ARTIFACT_URI_TAG not in mlflow.tags


# ---------------------------------------------------------------------------
# Integration: _dispatch_genai passes run_id and calls persist
# ---------------------------------------------------------------------------


def test_dispatch_genai_calls_persist_per_row(tmp_path: Path) -> None:
    """_dispatch_genai calls _persist_per_row_artifact with the result."""
    from src.evaluation.custom_eval import _dispatch_genai

    mock_result = SimpleNamespace(
        metrics={"accuracy": 0.9},
        result_df=_make_result_df(n=4),
    )

    captured_artifacts: list[tuple[str, str]] = []
    captured_tags: dict[str, str] = {}

    class _CapMlflow:
        def log_artifact(self, local_path: str, artifact_path: str = "") -> None:
            captured_artifacts.append((local_path, artifact_path))

        def set_tag(self, key: str, value: str) -> None:
            captured_tags[key] = value

    fake_mlflow_genai = SimpleNamespace(
        evaluate=lambda **kw: mock_result,
    )

    spec = _make_spec(scorer_ref=None)

    with patch.dict(sys.modules, {"mlflow.genai": fake_mlflow_genai}):
        result = _dispatch_genai(
            mlflow_module=_CapMlflow(),
            model_id="model-a",
            dataset_reference="s3://bucket/data.json",
            runtime_spec=spec,
            run_id="run-dispatch-001",
        )

    assert result is mock_result
    assert len(captured_artifacts) == 1
    assert captured_artifacts[0][1] == "eval_results"
    assert captured_tags[PER_ROW_ARTIFACT_URI_TAG] == (
        "runs:/run-dispatch-001/eval_results/per_row.parquet"
    )
