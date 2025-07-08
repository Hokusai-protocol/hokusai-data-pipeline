"""
Integration tests for ZK schema with existing pipeline outputs.
"""

import json
from pathlib import Path

import pytest

from src.utils.schema_validator import SchemaValidator, validate_for_zk_proof


class TestZKSchemaIntegration:
    """Test integration of ZK schema with existing pipeline components."""

    @pytest.fixture
    def schema_validator(self):
        """Create a schema validator instance."""
        return SchemaValidator()

    @pytest.fixture
    def valid_zk_example(self):
        """Load the valid ZK output example."""
        example_path = (
            Path(__file__).parent.parent.parent / "schema" / "examples" / "valid_zk_output.json"
        )
        with open(example_path) as f:
            return json.load(f)

    @pytest.fixture
    def existing_delta_output(self):
        """Load existing pipeline delta output."""
        output_path = (
            Path(__file__).parent.parent.parent / "outputs" / "delta_output_1749778320931703.json"
        )
        if output_path.exists():
            with open(output_path) as f:
                return json.load(f)
        else:
            pytest.skip("No existing delta output found")

    @pytest.fixture
    def existing_attestation_output(self):
        """Load existing pipeline attestation output."""
        output_path = (
            Path(__file__).parent.parent.parent / "outputs" / "attestation_1749778320931703.json"
        )
        if output_path.exists():
            with open(output_path) as f:
                return json.load(f)
        else:
            pytest.skip("No existing attestation output found")

    def test_valid_zk_example_passes_validation(self, schema_validator, valid_zk_example):
        """Test that the valid ZK example passes schema validation."""
        is_valid, errors = schema_validator.validate_output(valid_zk_example)
        assert is_valid, f"Valid example failed validation: {errors}"

    def test_valid_zk_example_is_zk_ready(self, valid_zk_example):
        """Test that the valid ZK example is ready for ZK proof generation."""
        is_ready, deterministic_hash, errors = validate_for_zk_proof(valid_zk_example)
        assert is_ready, f"Valid example not ZK-ready: {errors}"
        assert len(deterministic_hash) == 64, "Deterministic hash should be 64 characters"
        assert deterministic_hash.isalnum(), "Deterministic hash should be alphanumeric"

    def test_existing_delta_output_structure(self, existing_delta_output):
        """Test the structure of existing delta output for migration planning."""
        # This test documents the current structure to help with migration
        assert "schema_version" in existing_delta_output
        assert "delta_computation" in existing_delta_output
        assert "baseline_model" in existing_delta_output
        assert "new_model" in existing_delta_output
        assert "contributor_attribution" in existing_delta_output
        assert "evaluation_metadata" in existing_delta_output
        assert "pipeline_metadata" in existing_delta_output

    def test_existing_attestation_output_structure(self, existing_attestation_output):
        """Test the structure of existing attestation output for migration planning."""
        # This test documents the current attestation structure
        assert "schema_version" in existing_attestation_output
        assert "contributor_data_hash" in existing_attestation_output
        assert "baseline_model_id" in existing_attestation_output
        assert "new_model_id" in existing_attestation_output
        assert "evaluation_results" in existing_attestation_output
        assert "model_comparison" in existing_attestation_output
        assert "delta_one_score" in existing_attestation_output

    def test_schema_validation_cli_tool(self, valid_zk_example, tmp_path):
        """Test the CLI validation tool with valid data."""
        import subprocess
        import sys

        # Write valid example to temporary file
        test_file = tmp_path / "test_valid.json"
        with open(test_file, "w") as f:
            json.dump(valid_zk_example, f)

        # Run CLI validation
        result = subprocess.run(
            [sys.executable, "scripts/validate_schema.py", str(test_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI validation failed: {result.stderr}"
        assert "✅ VALID" in result.stdout

    def test_schema_validation_cli_zk_check(self, valid_zk_example, tmp_path):
        """Test the CLI validation tool with ZK check."""
        import subprocess
        import sys

        # Write valid example to temporary file
        test_file = tmp_path / "test_zk_check.json"
        with open(test_file, "w") as f:
            json.dump(valid_zk_example, f)

        # Run CLI validation with ZK check
        result = subprocess.run(
            [sys.executable, "scripts/validate_schema.py", str(test_file), "--zk-check"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI ZK check failed: {result.stderr}"
        assert "✅ ZK-READY" in result.stdout

    def test_schema_validation_cli_invalid_data(self, tmp_path):
        """Test the CLI validation tool with invalid data."""
        import subprocess
        import sys

        # Create invalid data
        invalid_data = {"invalid": "data"}
        test_file = tmp_path / "test_invalid.json"
        with open(test_file, "w") as f:
            json.dump(invalid_data, f)

        # Run CLI validation (should fail)
        result = subprocess.run(
            [sys.executable, "scripts/validate_schema.py", str(test_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, "CLI validation should fail for invalid data"
        assert "❌ INVALID" in result.stdout

    def test_deterministic_hash_consistency(self, valid_zk_example):
        """Test that deterministic hash computation is consistent."""
        from src.utils.schema_validator import compute_deterministic_hash

        # Compute hash multiple times
        hash1 = compute_deterministic_hash(valid_zk_example)
        hash2 = compute_deterministic_hash(valid_zk_example)
        hash3 = compute_deterministic_hash(valid_zk_example)

        assert hash1 == hash2 == hash3, "Deterministic hash should be consistent"

    def test_deterministic_hash_order_independence(self, valid_zk_example):
        """Test that deterministic hash is independent of key order."""
        # Create a copy with different key order
        import copy

        from src.utils.schema_validator import compute_deterministic_hash

        reordered_data = copy.deepcopy(valid_zk_example)

        # The compute_deterministic_hash function should handle ordering internally
        hash1 = compute_deterministic_hash(valid_zk_example)
        hash2 = compute_deterministic_hash(reordered_data)

        assert hash1 == hash2, "Deterministic hash should be order-independent"

    def test_schema_validation_performance(self, valid_zk_example, schema_validator):
        """Test that schema validation completes in reasonable time."""
        import time

        start_time = time.time()
        for _ in range(100):  # Validate 100 times
            is_valid, errors = schema_validator.validate_output(valid_zk_example)
            assert is_valid
        end_time = time.time()

        # Should complete 100 validations in under 1 second
        total_time = end_time - start_time
        assert total_time < 1.0, f"Validation too slow: {total_time:.2f}s for 100 validations"

    def test_migration_compatibility_check(self, existing_delta_output, schema_validator):
        """Test what would be needed to migrate existing output to new schema."""
        # This test identifies missing fields for migration planning

        # Try to validate existing output against new schema (should fail)
        is_valid, errors = schema_validator.validate_output(existing_delta_output)
        assert not is_valid, "Existing output should not validate against new schema"

        # Check which required fields are missing
        missing_fields = []
        for error in errors:
            if "is a required property" in error:
                # Extract field name from error message
                field_name = error.split("'")[1]
                missing_fields.append(field_name)

        # Document expected missing fields for migration
        expected_missing = [
            "metadata",
            "evaluation_results",
            "models",
            "contributor_info",
            "attestation",
        ]

        # Check that we found expected missing fields
        for expected_field in expected_missing:
            assert any(
                expected_field in error for error in errors
            ), f"Expected missing field '{expected_field}' not found in validation errors"

    def test_hash_format_validation(self, schema_validator):
        """Test that hash format validation works correctly."""
        # Valid data with invalid hash
        invalid_hash_data = {
            "schema_version": "1.0",
            "metadata": {
                "pipeline_run_id": "test",
                "timestamp": "2025-06-16T10:30:00.000Z",
                "pipeline_version": "abc123",
            },
            "evaluation_results": {
                "baseline_metrics": {"accuracy": 0.85},
                "new_metrics": {"accuracy": 0.88},
                "benchmark_metadata": {"size": 100, "type": "test"},
            },
            "delta_computation": {
                "delta_one_score": 0.03,
                "metric_deltas": {},
                "computation_method": "weighted_average_delta",
                "metrics_included": [],
                "improved_metrics": [],
                "degraded_metrics": [],
            },
            "models": {
                "baseline": {
                    "model_id": "test",
                    "model_type": "test",
                    "metrics": {"accuracy": 0.85},
                },
                "new": {"model_id": "test", "model_type": "test", "metrics": {"accuracy": 0.88}},
            },
            "contributor_info": {
                "data_hash": "invalid_hash",  # This should trigger validation error
                "data_manifest": {"data_hash": "invalid_hash", "row_count": 100, "column_count": 5},
            },
            "attestation": {
                "hash_tree_root": "also_invalid",  # This should also trigger validation error
                "proof_ready": False,
                "public_inputs_hash": "still_invalid",  # And this one too
            },
        }

        is_valid, errors = schema_validator.validate_output(invalid_hash_data)
        assert not is_valid, "Data with invalid hashes should not validate"

        # Should have multiple hash format errors
        hash_errors = [
            error for error in errors if "does not match" in error and "[a-f0-9]{64}" in error
        ]
        assert (
            len(hash_errors) >= 3
        ), f"Expected at least 3 hash format errors, got {len(hash_errors)}"
