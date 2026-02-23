from __future__ import annotations

from src.evaluation.validation import validate_manifest


def _valid_manifest() -> dict:
    return {
        "schema_version": "hokusai.eval.manifest/v1",
        "model_id": "model-a",
        "eval_id": "eval-001",
        "dataset": {"id": "dataset-1", "hash": "sha256:abc123", "num_samples": 100},
        "primary_metric": {"name": "accuracy", "value": 0.95, "higher_is_better": True},
        "metrics": [{"name": "accuracy", "value": 0.95, "higher_is_better": True}],
        "created_at": "2026-01-01T00:00:00Z",
        "mlflow_run_id": "run-123",
    }


def test_validate_manifest_accepts_required_fields_only() -> None:
    assert validate_manifest(_valid_manifest()) == []


def test_validate_manifest_accepts_optional_fields() -> None:
    manifest = _valid_manifest()
    manifest.update(
        {
            "mlflow_dataset_id": "dataset-mlflow-1",
            "uncertainty": {"method": "bootstrap", "ci95": [0.9, 0.98]},
            "artifacts": [{"name": "report", "path": "reports/out.json", "hash": "sha256:1"}],
            "provenance": {
                "provider": "openai_evals",
                "provider_version": "1.0.0",
                "parameters": {"temperature": 0.0},
            },
        }
    )
    assert validate_manifest(manifest) == []


def test_validate_manifest_rejects_missing_required_fields() -> None:
    manifest = _valid_manifest()
    del manifest["model_id"]
    errors = validate_manifest(manifest)
    assert errors
    assert "model_id" in errors[0]


def test_validate_manifest_rejects_invalid_field_types() -> None:
    manifest = _valid_manifest()
    manifest["dataset"]["num_samples"] = "100"
    errors = validate_manifest(manifest)
    assert errors
    assert any("num_samples" in error for error in errors)
