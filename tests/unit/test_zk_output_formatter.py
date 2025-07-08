"""Unit tests for ZK output formatter."""

import pytest
from unittest.mock import patch, MagicMock

from src.utils.zk_output_formatter import ZKCompatibleOutputFormatter


class TestZKCompatibleOutputFormatter:
    """Test the ZK-compatible output formatter."""

    @pytest.fixture
    def formatter(self):
        """Create a formatter instance."""
        return ZKCompatibleOutputFormatter()

    @pytest.fixture
    def sample_pipeline_results(self):
        """Sample pipeline results in existing format."""
        return {
            "schema_version": "1.0",
            "delta_computation": {
                "delta_one_score": 0.033157134026648195,
                "metric_deltas": {
                    "accuracy": {
                        "baseline_value": 0.854492577162388,
                        "new_value": 0.8840483940124245,
                        "absolute_delta": 0.029555816850036498,
                        "relative_delta": 0.0345887344606151,
                        "improvement": True
                    },
                    "f1": {
                        "baseline_value": 0.8389452328858691,
                        "new_value": 0.8911018964512049,
                        "absolute_delta": 0.05215666356533577,
                        "relative_delta": 0.06216933063189741,
                        "improvement": True
                    }
                },
                "computation_method": "weighted_average_delta",
                "metrics_included": ["accuracy", "f1"],
                "improved_metrics": ["accuracy", "f1"],
                "degraded_metrics": []
            },
            "baseline_model": {
                "model_id": "1.0.0",
                "model_type": "mock_model",
                "metrics": {
                    "accuracy": 0.854492577162388,
                    "f1": 0.8389452328858691
                },
                "mlflow_run_id": None
            },
            "new_model": {
                "model_id": "2.0.0",
                "model_type": "mock_hokusai_integrated_classifier",
                "metrics": {
                    "accuracy": 0.8840483940124245,
                    "f1": 0.8911018964512049
                },
                "mlflow_run_id": "test_run_id",
                "training_metadata": {
                    "base_samples": 500,
                    "contributed_samples": 100,
                    "contribution_ratio": 0.16666666666666666,
                    "data_manifest": {
                        "source_path": "data/test_fixtures/test_queries.csv",
                        "row_count": 100,
                        "column_count": 6,
                        "columns": ["query_id", "query_text", "feature_1", "feature_2", "feature_3", "label"],
                        "data_hash": "3b26f05d3923476fb7eeedd1bee22e4e6b8c19566fe0f61f45c7ea48d7242e7e",
                        "dtypes": {"query_id": "object", "query_text": "object"},
                        "null_counts": {"query_id": 0, "query_text": 0},
                        "unique_counts": {"query_id": 100, "query_text": 100}
                    }
                }
            },
            "contributor_attribution": {
                "data_hash": "3b26f05d3923476fb7eeedd1bee22e4e6b8c19566fe0f61f45c7ea48d7242e7e",
                "contributor_weights": 0.16666666666666666,
                "contributed_samples": 100,
                "total_samples": 600,
                "data_manifest": {
                    "source_path": "data/test_fixtures/test_queries.csv",
                    "row_count": 100,
                    "column_count": 6,
                    "columns": ["query_id", "query_text", "feature_1", "feature_2", "feature_3", "label"],
                    "data_hash": "3b26f05d3923476fb7eeedd1bee22e4e6b8c19566fe0f61f45c7ea48d7242e7e",
                    "dtypes": {"query_id": "object", "query_text": "object"},
                    "null_counts": {"query_id": 0, "query_text": 0},
                    "unique_counts": {"query_id": 100, "query_text": 100}
                }
            },
            "evaluation_metadata": {
                "benchmark_dataset": {
                    "size": 1000,
                    "features": ["feature_1", "feature_2", "feature_3"],
                    "type": "mock_classification_benchmark"
                },
                "evaluation_timestamp": "2025-06-13T01:32:05.672891",
                "evaluation_time_seconds": 0.002335071563720703,
                "pipeline_run_id": "1749778320931703"
            },
            "pipeline_metadata": {
                "run_id": "1749778320931703",
                "timestamp": "2025-06-13T01:32:06.868547",
                "config": {
                    "environment": "test",
                    "log_level": "INFO",
                    "dry_run": True
                },
                "dry_run": True
            }
        }

    def test_format_output_structure(self, formatter, sample_pipeline_results):
        """Test that format_output returns correct structure."""
        result = formatter.format_output(sample_pipeline_results)

        # Check required top-level fields
        assert "schema_version" in result
        assert "metadata" in result
        assert "evaluation_results" in result
        assert "delta_computation" in result
        assert "models" in result
        assert "contributor_info" in result
        assert "attestation" in result

        # Check schema version
        assert result["schema_version"] == "1.0"

    def test_format_metadata(self, formatter, sample_pipeline_results):
        """Test metadata formatting."""
        result = formatter.format_output(sample_pipeline_results)
        metadata = result["metadata"]

        assert "pipeline_run_id" in metadata
        assert "timestamp" in metadata
        assert "pipeline_version" in metadata
        assert "environment" in metadata
        assert "dry_run" in metadata

        assert metadata["pipeline_run_id"] == "1749778320931703"
        assert metadata["environment"] == "test"
        assert metadata["dry_run"] is True
        assert metadata["timestamp"].endswith("Z")

    def test_format_evaluation_results(self, formatter, sample_pipeline_results):
        """Test evaluation results formatting."""
        result = formatter.format_output(sample_pipeline_results)
        eval_results = result["evaluation_results"]

        assert "baseline_metrics" in eval_results
        assert "new_metrics" in eval_results
        assert "benchmark_metadata" in eval_results

        # Check metrics are preserved
        assert eval_results["baseline_metrics"]["accuracy"] == 0.854492577162388
        assert eval_results["new_metrics"]["accuracy"] == 0.8840483940124245

        # Check benchmark metadata
        benchmark = eval_results["benchmark_metadata"]
        assert benchmark["size"] == 1000
        assert benchmark["type"] == "mock_classification_benchmark"
        assert "dataset_hash" in benchmark
        assert len(benchmark["dataset_hash"]) == 64  # SHA-256 hash length

    def test_format_delta_computation(self, formatter, sample_pipeline_results):
        """Test delta computation formatting."""
        result = formatter.format_output(sample_pipeline_results)
        delta_comp = result["delta_computation"]

        assert "delta_one_score" in delta_comp
        assert "metric_deltas" in delta_comp
        assert "computation_method" in delta_comp
        assert "metrics_included" in delta_comp
        assert "improved_metrics" in delta_comp
        assert "degraded_metrics" in delta_comp

        # Check delta score is preserved
        assert delta_comp["delta_one_score"] == 0.033157134026648195

        # Check metric deltas structure
        accuracy_delta = delta_comp["metric_deltas"]["accuracy"]
        assert "baseline_value" in accuracy_delta
        assert "new_value" in accuracy_delta
        assert "absolute_delta" in accuracy_delta
        assert "relative_delta" in accuracy_delta
        assert "improvement" in accuracy_delta
        assert accuracy_delta["improvement"] is True

    def test_format_models(self, formatter, sample_pipeline_results):
        """Test models formatting."""
        result = formatter.format_output(sample_pipeline_results)
        models = result["models"]

        assert "baseline" in models
        assert "new" in models

        # Check baseline model
        baseline = models["baseline"]
        assert baseline["model_id"] == "1.0.0"
        assert baseline["model_type"] == "mock_model"
        assert "model_hash" in baseline
        assert "training_config_hash" in baseline
        assert baseline["mlflow_run_id"] is None
        assert "metrics" in baseline

        # Check new model
        new_model = models["new"]
        assert new_model["model_id"] == "2.0.0"
        assert new_model["model_type"] == "mock_hokusai_integrated_classifier"
        assert new_model["mlflow_run_id"] == "test_run_id"
        assert "training_metadata" in new_model

        # Check training metadata structure
        training_meta = new_model["training_metadata"]
        assert training_meta["base_samples"] == 500
        assert training_meta["contributed_samples"] == 100
        assert "data_manifest" in training_meta

    def test_format_contributor_info(self, formatter, sample_pipeline_results):
        """Test contributor info formatting."""
        result = formatter.format_output(sample_pipeline_results)
        contrib_info = result["contributor_info"]

        assert "data_hash" in contrib_info
        assert "data_manifest" in contrib_info
        assert "contributor_weights" in contrib_info
        assert "contributed_samples" in contrib_info
        assert "total_samples" in contrib_info
        assert "validation_status" in contrib_info

        assert contrib_info["data_hash"] == "3b26f05d3923476fb7eeedd1bee22e4e6b8c19566fe0f61f45c7ea48d7242e7e"
        assert contrib_info["contributed_samples"] == 100
        assert contrib_info["total_samples"] == 600
        assert contrib_info["validation_status"] == "valid"

        # Check data manifest structure
        manifest = contrib_info["data_manifest"]
        assert manifest["row_count"] == 100
        assert manifest["column_count"] == 6
        assert len(manifest["columns"]) == 6

    def test_format_attestation(self, formatter, sample_pipeline_results):
        """Test attestation formatting."""
        result = formatter.format_output(sample_pipeline_results)
        attestation = result["attestation"]

        assert "hash_tree_root" in attestation
        assert "proof_ready" in attestation
        assert "signature_blob" in attestation
        assert "verification_key" in attestation
        assert "proof_system" in attestation
        assert "circuit_hash" in attestation
        assert "public_inputs_hash" in attestation

        assert len(attestation["hash_tree_root"]) == 64  # SHA-256 hash
        assert attestation["proof_ready"] is True
        assert attestation["signature_blob"] is None
        assert attestation["proof_system"] == "none"
        assert len(attestation["public_inputs_hash"]) == 64  # SHA-256 hash

    def test_hash_consistency(self, formatter, sample_pipeline_results):
        """Test that hashes are consistent across multiple runs."""
        result1 = formatter.format_output(sample_pipeline_results)
        result2 = formatter.format_output(sample_pipeline_results)

        # Hashes should be identical for same input
        assert result1["attestation"]["hash_tree_root"] == result2["attestation"]["hash_tree_root"]
        assert result1["attestation"]["public_inputs_hash"] == result2["attestation"]["public_inputs_hash"]
        assert result1["models"]["baseline"]["model_hash"] == result2["models"]["baseline"]["model_hash"]

    @patch("src.utils.zk_output_formatter.subprocess.run")
    def test_git_commit_hash_success(self, mock_subprocess, formatter):
        """Test successful git commit hash retrieval."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abcd1234567890abcdef\n"
        mock_subprocess.return_value = mock_result

        hash_value = formatter._get_git_commit_hash()
        assert hash_value == "abcd1234"  # First 8 characters

    @patch("src.utils.zk_output_formatter.subprocess.run")
    def test_git_commit_hash_failure(self, mock_subprocess, formatter):
        """Test git commit hash retrieval failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_subprocess.return_value = mock_result

        hash_value = formatter._get_git_commit_hash()
        assert hash_value == "unknown"

    def test_timestamp_formatting(self, formatter):
        """Test timestamp formatting."""
        # Test with timestamp without Z
        timestamp1 = formatter._format_timestamp("2025-06-13T01:32:05.672891")
        assert timestamp1 == "2025-06-13T01:32:05Z"

        # Test with timestamp already having Z
        timestamp2 = formatter._format_timestamp("2025-06-13T01:32:05Z")
        assert timestamp2 == "2025-06-13T01:32:05Z"

        # Test with None timestamp
        timestamp3 = formatter._format_timestamp(None)
        assert timestamp3.endswith("Z")

    def test_format_and_validate_success(self, formatter, sample_pipeline_results):
        """Test format_and_validate with valid data."""
        with patch.object(formatter.validator, "validate_output", return_value=(True, [])):
            with patch("src.utils.zk_output_formatter.validate_for_zk_proof",
                      return_value=(True, "abcd1234" * 8, [])):

                formatted_output, is_valid, errors = formatter.format_and_validate(sample_pipeline_results)

                assert is_valid is True
                assert len(errors) == 0
                assert formatted_output["attestation"]["public_inputs_hash"] == "abcd1234" * 8

    def test_format_and_validate_schema_failure(self, formatter, sample_pipeline_results):
        """Test format_and_validate with schema validation failure."""
        with patch.object(formatter.validator, "validate_output",
                         return_value=(False, ["Schema validation error"])):

            formatted_output, is_valid, errors = formatter.format_and_validate(sample_pipeline_results)

            assert is_valid is False
            assert "Schema validation error" in errors

    def test_format_and_validate_zk_failure(self, formatter, sample_pipeline_results):
        """Test format_and_validate with ZK validation failure."""
        with patch.object(formatter.validator, "validate_output", return_value=(True, [])):
            with patch("src.utils.zk_output_formatter.validate_for_zk_proof",
                      return_value=(False, None, ["ZK validation error"])):

                formatted_output, is_valid, errors = formatter.format_and_validate(sample_pipeline_results)

                assert is_valid is False
                assert "ZK validation error" in errors

    def test_compute_model_hash(self, formatter):
        """Test model hash computation."""
        model_info1 = {
            "model_id": "test_model",
            "model_type": "test_type",
            "metrics": {"accuracy": 0.85}
        }

        model_info2 = {
            "model_id": "test_model",
            "model_type": "test_type",
            "metrics": {"accuracy": 0.85}
        }

        model_info3 = {
            "model_id": "different_model",
            "model_type": "test_type",
            "metrics": {"accuracy": 0.85}
        }

        hash1 = formatter._compute_model_hash(model_info1)
        hash2 = formatter._compute_model_hash(model_info2)
        hash3 = formatter._compute_model_hash(model_info3)

        assert hash1 == hash2  # Same model should have same hash
        assert hash1 != hash3  # Different model should have different hash
        assert len(hash1) == 64  # SHA-256 hash length

    def test_empty_input_handling(self, formatter):
        """Test handling of empty or minimal input."""
        minimal_input = {}

        result = formatter.format_output(minimal_input)

        # Should still produce valid structure with defaults
        assert "schema_version" in result
        assert "metadata" in result
        assert "evaluation_results" in result
        assert "delta_computation" in result
        assert "models" in result
        assert "contributor_info" in result
        assert "attestation" in result

        # Check default values
        assert result["metadata"]["pipeline_run_id"] == "unknown"
        assert result["metadata"]["environment"] == "unknown"
        assert result["delta_computation"]["delta_one_score"] == 0.0
        assert result["evaluation_results"]["baseline_metrics"] == {}

    def test_deterministic_hash_computation(self, formatter):
        """Test that deterministic hash computation is order-independent."""
        data1 = {"b": 2, "a": 1, "c": 3}
        data2 = {"a": 1, "b": 2, "c": 3}

        hash1 = formatter._compute_deterministic_hash(data1)
        hash2 = formatter._compute_deterministic_hash(data2)

        assert hash1 == hash2  # Should be identical despite different order
        assert len(hash1) == 64  # SHA-256 hash length
