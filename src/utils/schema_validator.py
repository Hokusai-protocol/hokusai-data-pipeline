"""JSON Schema validation utilities for ZK-compatible Hokusai pipeline outputs.

This module provides validation functions for ensuring pipeline outputs conform
to the standardized schema required for zero-knowledge proof generation and
on-chain verification.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from jsonschema import Draft202012Validator, ValidationError, validate


class SchemaValidator:
    """Validates Hokusai pipeline outputs against the ZK-compatible schema."""

    def __init__(self, schema_path: Optional[str] = None) -> None:
        """Initialize the schema validator.

        Args:
            schema_path: Path to the JSON schema file. If None, uses default schema.

        """
        if schema_path is None:
            # Default to schema in the project root
            project_root = Path(__file__).parent.parent.parent
            schema_path = project_root / "schema" / "zk_output_schema.json"

        self.schema_path = Path(schema_path)
        self.schema = self._load_schema()
        self.validator = Draft202012Validator(self.schema)

    def _load_schema(self) -> dict[str, Any]:
        """Load and parse the JSON schema."""
        try:
            with open(self.schema_path) as f:
                schema = json.load(f)
            return schema
        except FileNotFoundError:
            raise FileNotFoundError(f"Schema file not found: {self.schema_path}") from None
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in schema file: {e}") from e

    def validate_output(self, output_data: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate a pipeline output against the schema.

        Args:
            output_data: The pipeline output data to validate

        Returns:
            Tuple of (is_valid, error_messages)

        """
        errors = []

        try:
            # Validate against the schema
            validate(instance=output_data, schema=self.schema)

            # Additional ZK-specific validations
            zk_errors = self._validate_zk_requirements(output_data)
            errors.extend(zk_errors)

            return len(errors) == 0, errors

        except ValidationError as e:
            errors.append(f"Schema validation error: {e.message}")
            return False, errors
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            return False, errors

    def _validate_zk_requirements(self, data: dict[str, Any]) -> list[str]:
        """Perform additional ZK-specific validations beyond the schema.

        Args:
            data: The output data to validate

        Returns:
            List of validation error messages

        """
        errors = []

        # Validate hash formats and consistency
        hash_errors = self._validate_hashes(data)
        errors.extend(hash_errors)

        # Validate deterministic serialization requirements
        determinism_errors = self._validate_deterministic_fields(data)
        errors.extend(determinism_errors)

        # Validate attestation readiness
        attestation_errors = self._validate_attestation_fields(data)
        errors.extend(attestation_errors)

        return errors

    def _validate_hashes(self, data: dict[str, Any]) -> list[str]:
        """Validate hash field formats and consistency."""
        errors = []

        # Check that all hash fields are valid SHA-256 hashes
        hash_fields = [
            ("contributor_info", "data_hash"),
            ("attestation", "hash_tree_root"),
            ("attestation", "public_inputs_hash"),
        ]

        for field_path in hash_fields:
            try:
                value = data
                for key in field_path:
                    value = value[key]

                if not self._is_valid_sha256(value):
                    field_name = ".".join(field_path)
                    errors.append(f"Invalid SHA-256 hash format for {field_name}: {value}")
            except KeyError:
                # Optional fields may not be present
                continue

        return errors

    def _is_valid_sha256(self, hash_str: str) -> bool:
        """Check if a string is a valid SHA-256 hash."""
        if not isinstance(hash_str, str):
            return False
        if len(hash_str) != 64:
            return False
        try:
            int(hash_str, 16)
            return True
        except ValueError:
            return False

    def _validate_deterministic_fields(self, data: dict[str, Any]) -> list[str]:
        """Validate that fields required for deterministic serialization are present."""
        errors = []

        # Check that all required fields for ZK proofs are present and properly formatted
        required_for_zk = [
            ("metadata", "pipeline_run_id"),
            ("metadata", "timestamp"),
            ("delta_computation", "delta_one_score"),
            ("contributor_info", "data_hash"),
        ]

        for field_path in required_for_zk:
            try:
                value = data
                for key in field_path:
                    value = value[key]

                # Additional checks for specific field types
                field_name = ".".join(field_path)
                if field_name.endswith("timestamp") and not self._is_valid_iso8601(str(value)):
                    errors.append(f"Invalid ISO 8601 timestamp format for {field_name}")

            except KeyError:
                field_name = ".".join(field_path)
                errors.append(f"Required field missing for ZK proof: {field_name}")

        return errors

    def _is_valid_iso8601(self, timestamp_str: str) -> bool:
        """Check if a string is a valid ISO 8601 timestamp."""
        try:
            from datetime import datetime

            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False

    def _validate_attestation_fields(self, data: dict[str, Any]) -> list[str]:
        """Validate attestation-specific requirements."""
        errors = []

        try:
            attestation = data["attestation"]

            # If proof_ready is True, certain fields should be present
            if attestation.get("proof_ready", False):
                if not attestation.get("hash_tree_root"):
                    errors.append("hash_tree_root is required when proof_ready is True")

                if not attestation.get("public_inputs_hash"):
                    errors.append("public_inputs_hash is required when proof_ready is True")

            # Validate proof system compatibility
            proof_system = attestation.get("proof_system", "none")
            if proof_system != "none":
                if not attestation.get("verification_key"):
                    errors.append(f"verification_key is required for proof_system: {proof_system}")

        except KeyError:
            errors.append("Missing required attestation section")

        return errors

    def validate_file(self, file_path: str) -> tuple[bool, list[str]]:
        """Validate a JSON file against the schema.

        Args:
            file_path: Path to the JSON file to validate

        Returns:
            Tuple of (is_valid, error_messages)

        """
        try:
            with open(file_path) as f:
                data = json.load(f)
            return self.validate_output(data)
        except FileNotFoundError:
            return False, [f"File not found: {file_path}"]
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON in file {file_path}: {e}"]
        except Exception as e:
            return False, [f"Error validating file {file_path}: {str(e)}"]

    def get_schema_version(self) -> str:
        """Get the version of the schema being used."""
        return (
            self.schema.get("title", "Unknown")
            + " (Schema ID: "
            + self.schema.get("$id", "Unknown")
            + ")"
        )


def compute_deterministic_hash(data: dict[str, Any]) -> str:
    """Compute a deterministic hash of the output data for ZK proof generation.

    This function ensures that the same data always produces the same hash,
    which is critical for ZK proof verification.

    Args:
        data: The pipeline output data

    Returns:
        SHA-256 hash of the deterministically serialized data

    """
    # Create a canonical representation by sorting keys recursively
    canonical_data = _sort_dict_recursively(data)

    # Serialize to JSON with consistent formatting
    json_str = json.dumps(canonical_data, separators=(",", ":"), sort_keys=True)

    # Compute SHA-256 hash
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def _sort_dict_recursively(obj: Any) -> Any:
    """Recursively sort dictionary keys for deterministic serialization."""
    if isinstance(obj, dict):
        return {k: _sort_dict_recursively(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [_sort_dict_recursively(item) for item in obj]
    else:
        return obj


def validate_for_zk_proof(output_data: dict[str, Any]) -> tuple[bool, str, list[str]]:
    """Comprehensive validation for ZK proof readiness.

    Args:
        output_data: The pipeline output data

    Returns:
        Tuple of (is_ready, deterministic_hash, error_messages)

    """
    validator = SchemaValidator()
    is_valid, errors = validator.validate_output(output_data)

    if not is_valid:
        return False, "", errors

    # Compute deterministic hash for ZK proof
    try:
        det_hash = compute_deterministic_hash(output_data)
        return True, det_hash, []
    except Exception as e:
        return False, "", [f"Error computing deterministic hash: {str(e)}"]
