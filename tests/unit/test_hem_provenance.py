"""Unit tests for HEM provenance fields and hash_scorer_source helper."""

from __future__ import annotations

from src.evaluation.manifest import HokusaiEvaluationManifest, hash_scorer_source
from src.evaluation.validation import validate_manifest

_BASE_MANIFEST_DICT = {
    "schema_version": "hokusai.eval.manifest/v1",
    "model_id": "model-x",
    "eval_id": "eval-001",
    "dataset": {"id": "ds-1", "hash": "sha256:abc", "num_samples": 10},
    "primary_metric": {"name": "accuracy", "value": 0.9},
    "metrics": [{"name": "accuracy", "value": 0.9}],
    "created_at": "2024-01-01T00:00:00Z",
    "mlflow_run_id": "run-001",
}


def _base_manifest(**overrides: object) -> HokusaiEvaluationManifest:
    return HokusaiEvaluationManifest(
        model_id="model-x",
        eval_id="eval-001",
        dataset={"id": "ds-1", "hash": "sha256:abc", "num_samples": 10},
        primary_metric={"name": "accuracy", "value": 0.9},
        metrics=[{"name": "accuracy", "value": 0.9}],
        mlflow_run_id="run-001",
        **overrides,
    )


class TestHashScorerSource:
    def test_is_deterministic(self) -> None:
        h1 = hash_scorer_source("def score(x): return 1")
        h2 = hash_scorer_source("def score(x): return 1")
        assert h1 == h2

    def test_normalizes_crlf_and_trailing_whitespace(self) -> None:
        src_a = "def score(x):\r\n    return 1\r\n"
        src_b = "def score(x):\n    return 1\n"
        assert hash_scorer_source(src_a) == hash_scorer_source(src_b)

    def test_normalizes_leading_trailing_whitespace(self) -> None:
        src_a = "  def score(x): return 1  "
        src_b = "def score(x): return 1"
        assert hash_scorer_source(src_a) == hash_scorer_source(src_b)

    def test_distinguishes_different_sources(self) -> None:
        h1 = hash_scorer_source("def score(x): return 1")
        h2 = hash_scorer_source("def score(x): return 0")
        assert h1 != h2

    def test_empty_string_returns_64_char_hex(self) -> None:
        result = hash_scorer_source("")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestManifestRoundtrip:
    def test_roundtrip_with_all_provenance_fields(self) -> None:
        manifest = _base_manifest(
            scorer_refs=[{"name": "my-scorer", "version": "1.0", "kind": "custom"}],
            scorer_source_hashes={"my-scorer": "abc123"},
            measurement_policy={"aggregation": "mean", "thresholds": {"min": 0.8}},
            guardrail_results=[{"name": "toxicity", "status": "pass"}],
            eval_spec_version="v2",
            input_dataset_hash="sha256:input",
            label_snapshot_hash="sha256:labels",
            coverage={"row_count": 1000, "label_coverage": 0.95},
        )

        data = manifest.to_dict()
        restored = HokusaiEvaluationManifest.from_dict(data)

        assert restored.scorer_refs == manifest.scorer_refs
        assert restored.scorer_source_hashes == manifest.scorer_source_hashes
        assert restored.measurement_policy == manifest.measurement_policy
        assert restored.guardrail_results == manifest.guardrail_results
        assert restored.eval_spec_version == manifest.eval_spec_version
        assert restored.input_dataset_hash == manifest.input_dataset_hash
        assert restored.label_snapshot_hash == manifest.label_snapshot_hash
        assert restored.coverage == manifest.coverage

    def test_backward_compat_legacy_fields_only(self) -> None:
        manifest = HokusaiEvaluationManifest.from_dict(_BASE_MANIFEST_DICT)

        assert manifest.scorer_refs == []
        assert manifest.scorer_source_hashes == {}
        assert manifest.measurement_policy is None
        assert manifest.guardrail_results == []
        assert manifest.eval_spec_version is None
        assert manifest.input_dataset_hash is None
        assert manifest.label_snapshot_hash is None
        assert manifest.coverage is None

    def test_to_dict_omits_empty_collections(self) -> None:
        manifest = _base_manifest()
        data = manifest.to_dict()

        assert "scorer_refs" not in data
        assert "scorer_source_hashes" not in data
        assert "guardrail_results" not in data
        assert "measurement_policy" not in data
        assert "eval_spec_version" not in data


class TestSchemaValidation:
    def test_accepts_fully_populated_provenance(self) -> None:
        data = {
            **_BASE_MANIFEST_DICT,
            "scorer_refs": [{"name": "my-scorer", "kind": "builtin"}],
            "scorer_source_hashes": {"my-scorer": "abc123def"},
            "measurement_policy": {"aggregation": "mean"},
            "guardrail_results": [{"name": "toxicity", "status": "pass"}],
            "eval_spec_version": "v1",
            "input_dataset_hash": "sha256:input",
            "label_snapshot_hash": "sha256:labels",
            "coverage": {"row_count": 500, "label_coverage": 0.9, "notes": "ok"},
        }
        errors = validate_manifest(data)
        assert errors == []

    def test_rejects_invalid_guardrail_status(self) -> None:
        data = {
            **_BASE_MANIFEST_DICT,
            "guardrail_results": [{"name": "toxicity", "status": "bogus"}],
        }
        errors = validate_manifest(data)
        assert len(errors) > 0

    def test_rejects_invalid_scorer_kind(self) -> None:
        data = {
            **_BASE_MANIFEST_DICT,
            "scorer_refs": [{"name": "my-scorer", "kind": "unknown"}],
        }
        errors = validate_manifest(data)
        assert len(errors) > 0
