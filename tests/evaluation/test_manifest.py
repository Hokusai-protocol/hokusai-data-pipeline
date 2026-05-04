from __future__ import annotations

import json

import pytest

from src.evaluation.manifest import HEM_SCHEMA_VERSION, HokusaiEvaluationManifest


def _base_manifest_kwargs() -> dict:
    return {
        "model_id": "model-a",
        "eval_id": "eval-001",
        "dataset": {"id": "dataset-1", "hash": "sha256:abc123", "num_samples": 100},
        "primary_metric": {"name": "accuracy", "value": 0.95, "higher_is_better": True},
        "metrics": [
            {"name": "accuracy", "value": 0.95, "higher_is_better": True},
            {"name": "f1", "value": 0.91, "higher_is_better": True},
        ],
        "mlflow_run_id": "run-123",
    }


def test_manifest_construction_with_required_fields() -> None:
    manifest = HokusaiEvaluationManifest(**_base_manifest_kwargs())
    payload = manifest.to_dict()
    assert payload["schema_version"] == HEM_SCHEMA_VERSION
    assert payload["model_id"] == "model-a"
    assert payload["dataset"]["hash"] == "sha256:abc123"
    assert payload["mlflow_run_id"] == "run-123"
    assert "created_at" in payload


def test_to_dict_from_dict_roundtrip() -> None:
    manifest = HokusaiEvaluationManifest(**_base_manifest_kwargs())
    payload = manifest.to_dict()
    restored = HokusaiEvaluationManifest.from_dict(payload)
    assert restored.to_dict() == payload


def test_compute_hash_is_deterministic_and_excludes_runtime_fields() -> None:
    first = HokusaiEvaluationManifest(**_base_manifest_kwargs(), created_at="2026-01-01T00:00:00Z")
    second = HokusaiEvaluationManifest(**_base_manifest_kwargs(), created_at="2026-01-02T00:00:00Z")
    second.mlflow_run_id = "run-456"
    assert first.compute_hash() == second.compute_hash()


def test_compute_hash_changes_when_content_changes() -> None:
    first = HokusaiEvaluationManifest(**_base_manifest_kwargs())
    changed = HokusaiEvaluationManifest(
        **{
            **_base_manifest_kwargs(),
            "dataset": {"id": "dataset-1", "hash": "sha256:zzz", "num_samples": 100},
        }
    )
    assert first.compute_hash() != changed.compute_hash()


def test_is_comparable_to_positive_and_negative_cases() -> None:
    first = HokusaiEvaluationManifest(**_base_manifest_kwargs())
    same = HokusaiEvaluationManifest(**{**_base_manifest_kwargs(), "mlflow_run_id": "run-999"})
    different_eval = HokusaiEvaluationManifest(**{**_base_manifest_kwargs(), "eval_id": "eval-002"})
    different_dataset = HokusaiEvaluationManifest(
        **{
            **_base_manifest_kwargs(),
            "dataset": {"id": "dataset-1", "hash": "sha256:different", "num_samples": 100},
        }
    )
    different_metric = HokusaiEvaluationManifest(
        **{**_base_manifest_kwargs(), "primary_metric": {"name": "f1", "value": 0.91}}
    )

    assert first.is_comparable_to(same)
    assert not first.is_comparable_to(different_eval)
    assert not first.is_comparable_to(different_dataset)
    assert not first.is_comparable_to(different_metric)


def test_from_dict_rejects_invalid_manifest() -> None:
    payload = HokusaiEvaluationManifest(**_base_manifest_kwargs()).to_dict()
    del payload["dataset"]["hash"]
    with pytest.raises(ValueError, match="Invalid HokusaiEvaluationManifest"):
        HokusaiEvaluationManifest.from_dict(payload)


def test_to_json_is_valid_json() -> None:
    manifest = HokusaiEvaluationManifest(**_base_manifest_kwargs())
    payload = manifest.to_json(indent=2)
    parsed = json.loads(payload)
    assert parsed["model_id"] == "model-a"


# ---------------------------------------------------------------------------
# per_row_artifact
# ---------------------------------------------------------------------------

_VALID_PER_ROW_ARTIFACT = {
    "uri": "runs:/run-123/eval_results/per_row.parquet",
    "schema": {"row_id": "object", "accuracy": "bool"},
    "row_count": 42,
    "sha256": "a" * 64,
}


def test_manifest_accepts_per_row_artifact() -> None:
    manifest = HokusaiEvaluationManifest(
        **_base_manifest_kwargs(), per_row_artifact=_VALID_PER_ROW_ARTIFACT
    )
    payload = manifest.to_dict()
    assert payload["per_row_artifact"]["row_count"] == 42
    assert payload["per_row_artifact"]["sha256"] == "a" * 64


def test_manifest_per_row_artifact_roundtrip() -> None:
    manifest = HokusaiEvaluationManifest(
        **_base_manifest_kwargs(), per_row_artifact=_VALID_PER_ROW_ARTIFACT
    )
    payload = manifest.to_dict()
    restored = HokusaiEvaluationManifest.from_dict(payload)
    assert restored.per_row_artifact == _VALID_PER_ROW_ARTIFACT
    assert restored.to_dict() == payload


def test_manifest_per_row_artifact_absent_when_none() -> None:
    manifest = HokusaiEvaluationManifest(**_base_manifest_kwargs(), per_row_artifact=None)
    payload = manifest.to_dict()
    assert "per_row_artifact" not in payload


def test_manifest_without_per_row_artifact_still_validates() -> None:
    manifest = HokusaiEvaluationManifest(**_base_manifest_kwargs())
    payload = manifest.to_dict()
    restored = HokusaiEvaluationManifest.from_dict(payload)
    assert restored.per_row_artifact is None


def test_manifest_from_dict_loads_per_row_artifact_none_when_field_absent() -> None:
    payload = HokusaiEvaluationManifest(**_base_manifest_kwargs()).to_dict()
    assert "per_row_artifact" not in payload
    restored = HokusaiEvaluationManifest.from_dict(payload)
    assert restored.per_row_artifact is None
