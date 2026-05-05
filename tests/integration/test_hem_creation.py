"""Integration tests for creating HEM from MLflow run data."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.evaluation.manifest import create_hem_from_mlflow_run
from src.evaluation.tags import PER_ROW_ARTIFACT_URI_TAG


def _fake_run() -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(run_id="run-123"),
        data=SimpleNamespace(
            tags={
                "hokusai.model_id": "model-a",
                "hokusai.eval_id": "eval-001",
                "hokusai.primary_metric": "accuracy",
                "hokusai.dataset.id": "dataset-1",
                "hokusai.dataset.hash": "sha256:abc123",
                "hokusai.dataset.num_samples": "42",
                "hokusai.provider": "mlflow_native",
            },
            params={"temperature": "0"},
            metrics={"z_metric": 0.4, "accuracy": 0.95, "f1": 0.91},
        ),
    )


def test_create_hem_from_mlflow_run_sorts_metrics_and_maps_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: _fake_run())
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123")

    assert manifest.eval_id == "eval-001"
    assert manifest.primary_metric["name"] == "accuracy"
    assert [metric["name"] for metric in manifest.metrics] == ["accuracy", "f1", "z_metric"]
    assert manifest.dataset == {"id": "dataset-1", "hash": "sha256:abc123", "num_samples": 42}


def test_create_hem_from_mlflow_run_allows_eval_id_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _fake_run()
    run.data.tags.pop("hokusai.eval_id")
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123", eval_id="eval-from-arg")

    assert manifest.eval_id == "eval-from-arg"


def test_create_hem_from_mlflow_run_rejects_non_numeric_dataset_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _fake_run()
    run.data.tags["hokusai.dataset.num_samples"] = "many"
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    with pytest.raises(ValueError, match="Invalid dataset sample count"):
        create_hem_from_mlflow_run("run-123")


def test_namespaced_primary_metric_carries_both_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical colon-namespaced name maps to underscore MLflow key."""
    run = SimpleNamespace(
        info=SimpleNamespace(run_id="run-456"),
        data=SimpleNamespace(
            tags={
                "hokusai.model_id": "model-b",
                "hokusai.eval_id": "eval-002",
                "hokusai.primary_metric": "workflow:success_rate_under_budget",
                "hokusai.dataset.id": "dataset-2",
                "hokusai.dataset.hash": "sha256:def456",
                "hokusai.dataset.num_samples": "100",
            },
            params={},
            metrics={"workflow_success_rate_under_budget": 0.85, "other_metric": 0.5},
        ),
    )
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-456")

    assert manifest.primary_metric["name"] == "workflow:success_rate_under_budget"
    assert manifest.primary_metric["mlflow_name"] == "workflow_success_rate_under_budget"
    assert manifest.primary_metric["value"] == 0.85


def test_safe_primary_metric_name_has_equal_name_and_mlflow_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When canonical name is already MLflow-safe, name == mlflow_name."""
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: _fake_run())
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123")

    assert manifest.primary_metric["name"] == "accuracy"
    assert manifest.primary_metric["mlflow_name"] == "accuracy"
    assert manifest.primary_metric["value"] == 0.95


def test_create_hem_from_mlflow_run_with_provenance_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provenance tags are extracted and surfaced in the resulting manifest."""
    run = _fake_run()
    run.data.tags["hokusai.eval_spec_version"] = "v2"
    run.data.tags["hokusai.input_dataset_hash"] = "sha256:inputhash"
    run.data.tags["hokusai.label_snapshot_hash"] = "sha256:labelshash"
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123")

    assert manifest.eval_spec_version == "v2"
    assert manifest.input_dataset_hash == "sha256:inputhash"
    assert manifest.label_snapshot_hash == "sha256:labelshash"


# ---------------------------------------------------------------------------
# per_row_artifact round-trip
# ---------------------------------------------------------------------------


def _make_parquet_in(directory: str, n_rows: int = 5) -> tuple[str, str]:
    """Write a test Parquet file and return (local_path, sha256_hex)."""
    df = pd.DataFrame(
        {
            "row_id": [str(i) for i in range(n_rows)],
            "accuracy": [True, False, True, True, False][:n_rows],
        }
    )
    path = Path(directory) / "per_row.parquet"
    df.to_parquet(str(path), index=False)
    sha256_hex = hashlib.sha256(path.read_bytes()).hexdigest()
    return str(path), sha256_hex


def test_create_hem_populates_per_row_artifact_when_tag_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_path, expected_sha = _make_parquet_in(str(tmp_path), n_rows=5)

    run = _fake_run()
    uri = "runs:/run-123/eval_results/per_row.parquet"
    run.data.tags[PER_ROW_ARTIFACT_URI_TAG] = uri

    def _download_artifacts(artifact_uri: str, dst_path: str) -> str:
        return local_path

    fake_artifacts = SimpleNamespace(download_artifacts=_download_artifacts)
    fake_mlflow = SimpleNamespace(
        get_run=lambda _run_id: run,
        artifacts=fake_artifacts,
    )
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123")

    assert manifest.per_row_artifact is not None
    assert manifest.per_row_artifact["row_count"] == 5
    assert manifest.per_row_artifact["sha256"] == expected_sha
    assert manifest.per_row_artifact["uri"] == uri
    assert "row_id" in manifest.per_row_artifact["schema"]


def test_create_hem_per_row_artifact_is_none_when_tag_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _fake_run()
    assert PER_ROW_ARTIFACT_URI_TAG not in run.data.tags
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123")

    assert manifest.per_row_artifact is None


def test_create_hem_per_row_artifact_is_none_when_download_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _fake_run()
    run.data.tags[PER_ROW_ARTIFACT_URI_TAG] = "runs:/run-123/eval_results/per_row.parquet"

    def _download_fails(artifact_uri: str, dst_path: str) -> str:
        raise RuntimeError("simulated download failure")

    fake_artifacts = SimpleNamespace(download_artifacts=_download_fails)
    fake_mlflow = SimpleNamespace(
        get_run=lambda _run_id: run,
        artifacts=fake_artifacts,
    )
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123")

    assert manifest.per_row_artifact is None
