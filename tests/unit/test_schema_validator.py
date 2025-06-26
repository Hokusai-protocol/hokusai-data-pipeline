"""
Unit tests for the schema validation utilities.
"""

import json
import pytest
from unittest.mock import patch

from src.utils.schema_validator import (
    SchemaValidator,
    compute_deterministic_hash,
    validate_for_zk_proof,
    _sort_dict_recursively
)


class TestSchemaValidator:
    """Test cases for the SchemaValidator class."""
    
    @pytest.fixture
    def validator(self):
        """Create a SchemaValidator instance for testing."""
        return SchemaValidator()
    
    @pytest.fixture
    def valid_output_data(self):
        """Sample valid output data for testing."""
        return {
            "schema_version": "1.0",
            "metadata": {
                "pipeline_run_id": "test_run_123",
                "timestamp": "2025-06-16T10:30:00.000Z",
                "pipeline_version": "abc123def456"
            },
            "evaluation_results": {
                "baseline_metrics": {
                    "accuracy": 0.85,
                    "precision": 0.82,
                    "recall": 0.88,
                    "f1": 0.84,
                    "auroc": 0.90
                },
                "new_metrics": {
                    "accuracy": 0.88,
                    "precision": 0.85,
                    "recall": 0.91,
                    "f1": 0.89,
                    "auroc": 0.93
                },
                "benchmark_metadata": {
                    "size": 1000,
                    "type": "test_benchmark"
                }
            },
            "delta_computation": {
                "delta_one_score": 0.033,
                "metric_deltas": {
                    "accuracy": {
                        "baseline_value": 0.85,
                        "new_value": 0.88,
                        "absolute_delta": 0.03,
                        "relative_delta": 0.035,
                        "improvement": True
                    }
                },
                "computation_method": "weighted_average_delta",
                "metrics_included": ["accuracy"],
                "improved_metrics": ["accuracy"],
                "degraded_metrics": []
            },
            "models": {
                "baseline": {
                    "model_id": "baseline_v1",
                    "model_type": "classifier",
                    "metrics": {
                        "accuracy": 0.85
                    }
                },
                "new": {
                    "model_id": "new_v1",
                    "model_type": "classifier",
                    "metrics": {
                        "accuracy": 0.88
                    }
                }
            },
            "contributor_info": {
                "data_hash": "abcd567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                "data_manifest": {
                    "data_hash": "abcd567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                    "row_count": 100,
                    "column_count": 5
                }
            },
            "attestation": {
                "hash_tree_root": "bcde567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                "proof_ready": True,
                "public_inputs_hash": "cdef567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
            }
        }
    
    def test_validator_initialization(self, validator):
        """Test that validator initializes correctly."""
        assert validator.schema is not None
        assert validator.validator is not None
        assert validator.schema_path.exists()
    
    def test_validate_valid_output(self, validator, valid_output_data):
        """Test validation of valid output data."""
        is_valid, errors = validator.validate_output(valid_output_data)
        assert is_valid
        assert len(errors) == 0
    
    def test_validate_missing_required_field(self, validator, valid_output_data):
        """Test validation when required fields are missing."""
        # Remove required field
        del valid_output_data["schema_version"]
        
        is_valid, errors = validator.validate_output(valid_output_data)
        assert not is_valid
        assert len(errors) > 0
        assert any("schema_version" in error for error in errors)
    
    def test_validate_invalid_hash_format(self, validator, valid_output_data):
        """Test validation of invalid hash formats."""
        # Set invalid hash (too short)
        valid_output_data["contributor_info"]["data_hash"] = "invalid_hash"
        
        is_valid, errors = validator.validate_output(valid_output_data)
        assert not is_valid
        assert len(errors) > 0
        # The error might be worded differently, so let's check for hash-related errors
        assert any("hash" in error.lower() or "sha" in error.lower() for error in errors)
    
    def test_validate_invalid_metric_range(self, validator, valid_output_data):
        """Test validation of metrics outside valid range."""
        # Set accuracy > 1.0
        valid_output_data["evaluation_results"]["baseline_metrics"]["accuracy"] = 1.5
        
        is_valid, errors = validator.validate_output(valid_output_data)
        assert not is_valid
        assert len(errors) > 0
    
    def test_validate_invalid_timestamp(self, validator, valid_output_data):
        """Test validation of invalid timestamp format."""
        valid_output_data["metadata"]["timestamp"] = "not-a-timestamp"
        
        is_valid, errors = validator.validate_output(valid_output_data)
        assert not is_valid
        assert any("Invalid ISO 8601 timestamp" in error for error in errors)
    
    def test_validate_zk_requirements_proof_ready_true(self, validator, valid_output_data):
        """Test ZK validation when proof_ready is True."""
        valid_output_data["attestation"]["proof_ready"] = True
        
        # Missing required field for proof_ready=True
        del valid_output_data["attestation"]["hash_tree_root"]
        
        is_valid, errors = validator.validate_output(valid_output_data)
        assert not is_valid
        assert len(errors) > 0
        # The error might be worded differently
        assert any("hash_tree_root" in error or "required" in error.lower() for error in errors)
    
    def test_validate_file_valid(self, validator, valid_output_data, tmp_path):
        """Test validation of a valid JSON file."""
        test_file = tmp_path / "test_output.json"
        test_file.write_text(json.dumps(valid_output_data))
        
        is_valid, errors = validator.validate_file(str(test_file))
        assert is_valid
        assert len(errors) == 0
    
    def test_validate_file_not_found(self, validator):
        """Test validation of non-existent file."""
        is_valid, errors = validator.validate_file("nonexistent.json")
        assert not is_valid
        assert any("File not found" in error for error in errors)
    
    def test_validate_file_invalid_json(self, validator, tmp_path):
        """Test validation of file with invalid JSON."""
        test_file = tmp_path / "invalid.json"
        test_file.write_text("{ invalid json")
        
        is_valid, errors = validator.validate_file(str(test_file))
        assert not is_valid
        assert any("Invalid JSON" in error for error in errors)
    
    def test_get_schema_version(self, validator):
        """Test getting schema version information."""
        version_info = validator.get_schema_version()
        assert isinstance(version_info, str)
        assert len(version_info) > 0


class TestDeterministicHashing:
    """Test cases for deterministic hashing functionality."""
    
    def test_compute_deterministic_hash_consistency(self):
        """Test that the same data always produces the same hash."""
        data = {
            "b": 2,
            "a": 1,
            "c": {"nested_b": "value2", "nested_a": "value1"}
        }
        
        hash1 = compute_deterministic_hash(data)
        hash2 = compute_deterministic_hash(data)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hash length
    
    def test_compute_deterministic_hash_order_independence(self):
        """Test that key order doesn't affect the hash."""
        data1 = {"a": 1, "b": 2, "c": 3}
        data2 = {"c": 3, "a": 1, "b": 2}
        
        hash1 = compute_deterministic_hash(data1)
        hash2 = compute_deterministic_hash(data2)
        
        assert hash1 == hash2
    
    def test_compute_deterministic_hash_different_data(self):
        """Test that different data produces different hashes."""
        data1 = {"a": 1, "b": 2}
        data2 = {"a": 1, "b": 3}
        
        hash1 = compute_deterministic_hash(data1)
        hash2 = compute_deterministic_hash(data2)
        
        assert hash1 != hash2
    
    def test_sort_dict_recursively(self):
        """Test recursive dictionary sorting."""
        data = {
            "z": {"y": 1, "x": 2},
            "a": [{"c": 3, "b": 4}],
            "m": 5
        }
        
        sorted_data = _sort_dict_recursively(data)
        
        # Check that top-level keys are sorted
        keys = list(sorted_data.keys())
        assert keys == ["a", "m", "z"]
        
        # Check that nested dict keys are sorted
        nested_keys = list(sorted_data["z"].keys())
        assert nested_keys == ["x", "y"]
        
        # Check that list contents are processed but order preserved
        assert sorted_data["a"][0] == {"b": 4, "c": 3}


class TestZKProofValidation:
    """Test cases for ZK proof validation functionality."""
    
    def test_validate_for_zk_proof_valid(self, valid_output_data):
        """Test ZK proof validation with valid data."""
        # Mock the SchemaValidator for this test
        with patch('src.utils.schema_validator.SchemaValidator') as mock_validator:
            mock_instance = mock_validator.return_value
            mock_instance.validate_output.return_value = (True, [])
            
            is_ready, det_hash, errors = validate_for_zk_proof(valid_output_data)
            
            assert is_ready
            assert len(det_hash) == 64  # SHA-256 hash length
            assert len(errors) == 0
    
    def test_validate_for_zk_proof_invalid_schema(self, valid_output_data):
        """Test ZK proof validation with schema validation errors."""
        with patch('src.utils.schema_validator.SchemaValidator') as mock_validator:
            mock_instance = mock_validator.return_value
            mock_instance.validate_output.return_value = (False, ["Schema error"])
            
            is_ready, det_hash, errors = validate_for_zk_proof(valid_output_data)
            
            assert not is_ready
            assert det_hash == ""
            assert "Schema error" in errors
    
    def test_validate_for_zk_proof_hash_computation_error(self, valid_output_data):
        """Test ZK proof validation when hash computation fails."""
        with patch('src.utils.schema_validator.SchemaValidator') as mock_validator:
            mock_instance = mock_validator.return_value
            mock_instance.validate_output.return_value = (True, [])
            
            with patch('src.utils.schema_validator.compute_deterministic_hash') as mock_hash:
                mock_hash.side_effect = Exception("Hash computation failed")
                
                is_ready, det_hash, errors = validate_for_zk_proof(valid_output_data)
                
                assert not is_ready
                assert det_hash == ""
                assert any("Error computing deterministic hash" in error for error in errors)


class TestSchemaValidatorHelpers:
    """Test cases for helper methods in SchemaValidator."""
    
    def test_is_valid_sha256(self):
        """Test SHA-256 hash validation."""
        validator = SchemaValidator()
        
        # Valid SHA-256 hash (exactly 64 characters, valid hex)
        valid_hash = "abcd567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        assert validator._is_valid_sha256(valid_hash)
        
        # Invalid cases
        assert not validator._is_valid_sha256("too_short")
        assert not validator._is_valid_sha256("g" * 64)  # Invalid hex characters
        assert not validator._is_valid_sha256(123)  # Not a string
        assert not validator._is_valid_sha256("a" * 63)  # Too short by 1
        assert not validator._is_valid_sha256("a" * 65)  # Too long by 1
    
    def test_is_valid_iso8601(self):
        """Test ISO 8601 timestamp validation."""
        validator = SchemaValidator()
        
        # Valid timestamps
        assert validator._is_valid_iso8601("2025-06-16T10:30:00.000Z")
        assert validator._is_valid_iso8601("2025-06-16T10:30:00+00:00")
        assert validator._is_valid_iso8601("2025-06-16T10:30:00")
        
        # Invalid timestamps
        assert not validator._is_valid_iso8601("not-a-timestamp")
        assert not validator._is_valid_iso8601("2025-13-01T10:30:00")  # Invalid month
        assert not validator._is_valid_iso8601("2025-06-32T10:30:00")  # Invalid day


@pytest.fixture
def valid_output_data():
    """Fixture providing valid output data for tests."""
    return {
        "schema_version": "1.0",
        "metadata": {
            "pipeline_run_id": "test_run_123",
            "timestamp": "2025-06-16T10:30:00.000Z",
            "pipeline_version": "abc123def456"
        },
        "evaluation_results": {
            "baseline_metrics": {
                "accuracy": 0.85
            },
            "new_metrics": {
                "accuracy": 0.88
            },
            "benchmark_metadata": {
                "size": 1000,
                "type": "test_benchmark"
            }
        },
        "delta_computation": {
            "delta_one_score": 0.033,
            "metric_deltas": {
                "accuracy": {
                    "baseline_value": 0.85,
                    "new_value": 0.88,
                    "absolute_delta": 0.03,
                    "relative_delta": 0.035,
                    "improvement": True
                }
            },
            "computation_method": "weighted_average_delta",
            "metrics_included": ["accuracy"],
            "improved_metrics": ["accuracy"],
            "degraded_metrics": []
        },
        "models": {
            "baseline": {
                "model_id": "baseline_v1",
                "model_type": "classifier",
                "metrics": {
                    "accuracy": 0.85
                }
            },
            "new": {
                "model_id": "new_v1",
                "model_type": "classifier",
                "metrics": {
                    "accuracy": 0.88
                }
            }
        },
        "contributor_info": {
            "data_hash": "abcd567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            "data_manifest": {
                "data_hash": "abcd567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                "row_count": 100,
                "column_count": 5
            }
        },
        "attestation": {
            "hash_tree_root": "bcde567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            "proof_ready": True,
            "public_inputs_hash": "cdef567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        }
    }