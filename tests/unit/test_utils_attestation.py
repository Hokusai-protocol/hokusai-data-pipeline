"""Unit tests for attestation utilities."""

import json
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from src.utils.attestation import AttestationGenerator, generate_attestation_hash
from src.utils.constants import ATTESTATION_SCHEMA_VERSION, ATTESTATION_VERSION


class TestGenerateAttestationHash:
    """Test suite for generate_attestation_hash function."""

    def test_generate_attestation_hash_basic(self):
        """Test basic attestation hash generation."""
        attestation = {"model_id": "test_model", "score": 0.95, "data": {"key": "value"}}

        hash1 = generate_attestation_hash(attestation)
        hash2 = generate_attestation_hash(attestation)

        # Should be deterministic
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_generate_attestation_hash_ignores_mutable_fields(self):
        """Test that mutable fields are ignored."""
        base_attestation = {"model_id": "test_model", "score": 0.95}

        attestation_with_mutable = base_attestation.copy()
        attestation_with_mutable["attestation_hash"] = "some_hash"
        attestation_with_mutable["timestamp"] = "2024-01-15T12:00:00Z"

        hash1 = generate_attestation_hash(base_attestation)
        hash2 = generate_attestation_hash(attestation_with_mutable)

        # Should produce same hash
        assert hash1 == hash2

    def test_generate_attestation_hash_order_independent(self):
        """Test that field order doesn't affect hash."""
        attestation1 = {"a": 1, "b": 2, "c": 3}

        attestation2 = {"c": 3, "a": 1, "b": 2}

        hash1 = generate_attestation_hash(attestation1)
        hash2 = generate_attestation_hash(attestation2)

        assert hash1 == hash2


class TestAttestationGenerator:
    """Test suite for AttestationGenerator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = AttestationGenerator()
        self.test_data = {
            "run_id": "test_run_123",
            "contributor_data_hash": "data_hash_abc",
            "baseline_model_id": "baseline_model_v1",
            "new_model_id": "improved_model_v2",
            "evaluation_results": {"accuracy": 0.95, "f1_score": 0.93},
            "delta_results": {"accuracy": 0.03, "f1_score": 0.02},
            "delta_score": 0.025,
        }

    def test_initialization(self):
        """Test generator initialization."""
        assert self.generator.schema_version == ATTESTATION_SCHEMA_VERSION
        assert self.generator.attestation_version == ATTESTATION_VERSION

    def test_create_attestation_structure(self):
        """Test attestation creation with all required fields."""
        attestation = self.generator.create_attestation(**self.test_data)

        # Check top-level fields
        assert attestation["schema_version"] == ATTESTATION_SCHEMA_VERSION
        assert attestation["attestation_version"] == ATTESTATION_VERSION
        assert attestation["run_id"] == "test_run_123"
        assert "attestation_id" in attestation
        assert "timestamp" in attestation
        assert "content_hash" in attestation

        # Check contributor section
        assert attestation["contributor"]["data_hash"] == "data_hash_abc"
        assert "contribution_timestamp" in attestation["contributor"]

        # Check models section
        assert attestation["models"]["baseline"]["model_id"] == "baseline_model_v1"
        assert "model_hash" in attestation["models"]["baseline"]
        assert attestation["models"]["improved"]["model_id"] == "improved_model_v2"
        assert "model_hash" in attestation["models"]["improved"]

        # Check evaluation section
        assert attestation["evaluation"]["metrics"] == self.test_data["evaluation_results"]
        assert attestation["evaluation"]["delta_results"] == self.test_data["delta_results"]
        assert attestation["evaluation"]["delta_score"] == 0.025

        # Check proof data
        assert "commitment" in attestation["proof_data"]
        assert "nullifier" in attestation["proof_data"]
        assert "public_inputs" in attestation["proof_data"]

    def test_create_attestation_with_metadata(self):
        """Test attestation creation with metadata."""
        metadata = {"experiment": "test_exp", "version": "1.0"}
        attestation = self.generator.create_attestation(**self.test_data, metadata=metadata)

        assert attestation["metadata"] == metadata

    def test_generate_attestation_id(self):
        """Test attestation ID generation."""
        with patch("src.utils.attestation.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2024-01-15T12:00:00"

            id1 = self.generator._generate_attestation_id("run_123")
            id2 = self.generator._generate_attestation_id("run_123")

            # Should be 16 characters
            assert len(id1) == 16
            assert len(id2) == 16

            # Same run_id at same time should produce same ID
            assert id1 == id2

    def test_hash_string(self):
        """Test string hashing."""
        test_string = "test_value"
        hash_result = self.generator._hash_string(test_string)

        # Should be SHA256 hex
        assert len(hash_result) == 64

        # Should be deterministic
        assert hash_result == self.generator._hash_string(test_string)

        # Different strings should produce different hashes
        assert hash_result != self.generator._hash_string("different_value")

    def test_generate_proof_data(self):
        """Test proof data generation."""
        proof_data = self.generator._generate_proof_data(
            "data_hash_long_string_for_testing", "baseline_id", "new_id", 0.025
        )

        assert "commitment" in proof_data
        assert "nullifier" in proof_data
        assert "merkle_root_placeholder" in proof_data
        assert proof_data["proof_type"] == "placeholder"
        assert proof_data["circuit_version"] == "1.0.0"

        # Check public inputs
        assert proof_data["public_inputs"]["delta_score"] == 0.025
        assert len(proof_data["public_inputs"]["data_hash"]) == 16  # Should be truncated
        assert proof_data["public_inputs"]["data_hash"] == "data_hash_long_s"  # First 16 chars
        assert isinstance(proof_data["public_inputs"]["timestamp"], int)

    def test_calculate_content_hash(self):
        """Test content hash calculation."""
        attestation = {
            "field1": "value1",
            "field2": "value2",
            "signature_placeholder": "0x000",
            "content_hash": "old_hash",
        }

        hash_result = self.generator._calculate_content_hash(attestation)

        # Should be deterministic
        assert hash_result == self.generator._calculate_content_hash(attestation)

        # Should ignore mutable fields
        attestation_copy = attestation.copy()
        attestation_copy["signature_placeholder"] = "0x111"
        attestation_copy["content_hash"] = "new_hash"

        assert hash_result == self.generator._calculate_content_hash(attestation_copy)

    def test_validate_attestation_valid(self):
        """Test validation of valid attestation."""
        attestation = self.generator.create_attestation(**self.test_data)

        # Should validate successfully
        assert self.generator.validate_attestation(attestation) is True

    def test_validate_attestation_missing_field(self):
        """Test validation with missing required field."""
        attestation = self.generator.create_attestation(**self.test_data)
        del attestation["contributor"]

        with pytest.raises(ValueError, match="Missing required field: contributor"):
            self.generator.validate_attestation(attestation)

    def test_validate_attestation_wrong_schema_version(self):
        """Test validation with wrong schema version."""
        attestation = self.generator.create_attestation(**self.test_data)
        attestation["schema_version"] = "999.0.0"

        with pytest.raises(ValueError, match="Invalid schema version"):
            self.generator.validate_attestation(attestation)

    def test_validate_attestation_invalid_content_hash(self):
        """Test validation with tampered content."""
        attestation = self.generator.create_attestation(**self.test_data)
        # Tamper with content
        attestation["evaluation"]["delta_score"] = 0.999

        with pytest.raises(ValueError, match="Content hash mismatch"):
            self.generator.validate_attestation(attestation)

    def test_save_attestation(self):
        """Test saving attestation to file."""
        attestation = self.generator.create_attestation(**self.test_data)
        output_path = Path("/tmp/test_attestation.json")

        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            with patch("pathlib.Path.mkdir") as mock_mkdir:
                result = self.generator.save_attestation(attestation, output_path)

                assert result == output_path
                mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
                mock_file.assert_called_once_with(output_path, "w")

                # Check that JSON was written
                handle = mock_file()
                written_data = "".join(call.args[0] for call in handle.write.call_args_list)
                parsed_data = json.loads(written_data)
                assert parsed_data["run_id"] == attestation["run_id"]

    def test_create_summary(self):
        """Test creating attestation summary."""
        attestation = self.generator.create_attestation(**self.test_data)
        summary = self.generator.create_summary(attestation)

        assert summary["attestation_id"] == attestation["attestation_id"]
        assert summary["timestamp"] == attestation["timestamp"]
        assert summary["delta_score"] == 0.025
        assert summary["improvement_percentage"] == 2.5
        assert summary["baseline_model"] == "baseline_model_v1"
        assert summary["improved_model"] == "improved_model_v2"
        assert summary["status"] == "IMPROVEMENT"

        # Check truncated fields
        assert summary["proof_commitment"].endswith("...")
        assert summary["content_hash"].endswith("...")

    def test_create_summary_no_improvement(self):
        """Test summary with no improvement."""
        self.test_data["delta_score"] = -0.01
        attestation = self.generator.create_attestation(**self.test_data)
        summary = self.generator.create_summary(attestation)

        assert summary["status"] == "NO_IMPROVEMENT"
        assert summary["improvement_percentage"] == -1.0
