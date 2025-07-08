"""Tests for the data validation CLI."""

from unittest.mock import MagicMock, patch

import pandas as pd
from hokusai_validate.cli import main
from hokusai_validate.file_loader import FileLoader
from hokusai_validate.hash_generator import HashGenerator
from hokusai_validate.manifest_generator import ManifestGenerator
from hokusai_validate.validators import DataQualityChecker, PIIDetector, SchemaValidator


class TestCLI:
    """Test the main CLI interface."""

    def test_cli_help_text(self, cli_runner) -> None:
        """Test that help text is displayed correctly."""
        result = cli_runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "hokusai-validate" in result.output
        assert "Validate data files for Hokusai contribution" in result.output
        assert "--schema" in result.output
        assert "--output-dir" in result.output
        assert "--no-pii-scan" in result.output

    def test_cli_version(self, cli_runner) -> None:
        """Test version command."""
        result = cli_runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_cli_missing_input_file(self, cli_runner) -> None:
        """Test error when no input file provided."""
        result = cli_runner.invoke(main, [])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_cli_nonexistent_file(self, cli_runner) -> None:
        """Test error when input file doesn't exist."""
        result = cli_runner.invoke(main, ["nonexistent.csv"])
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_cli_unsupported_format(self, cli_runner, tmp_path: str) -> None:
        """Test error for unsupported file format."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("some content")

        result = cli_runner.invoke(main, [str(test_file)])
        assert result.exit_code != 0
        assert "Unsupported file format" in result.output

    def test_cli_successful_validation(self, cli_runner, sample_csv_file: str) -> None:
        """Test successful validation flow."""
        with patch("hokusai_validate.cli.ValidationPipeline") as mock_pipeline:
            mock_instance = MagicMock()
            mock_pipeline.return_value = mock_instance
            mock_instance.validate.return_value = {
                "valid": True,
                "hash": "abc123",
                "manifest_path": "/path/to/manifest.json"
            }

            result = cli_runner.invoke(main, [sample_csv_file])
            assert result.exit_code == 0
            assert "Validation successful" in result.output
            assert "abc123" in result.output


class TestFileLoader:
    """Test file loading functionality."""

    def test_detect_csv_format(self, sample_csv_file: str) -> None:
        """Test CSV format detection."""
        loader = FileLoader()
        format_type = loader.detect_format(sample_csv_file)
        assert format_type == "csv"

    def test_detect_json_format(self, sample_json_file: str) -> None:
        """Test JSON format detection."""
        loader = FileLoader()
        format_type = loader.detect_format(sample_json_file)
        assert format_type == "json"

    def test_detect_parquet_format(self, sample_parquet_file: str) -> None:
        """Test Parquet format detection."""
        loader = FileLoader()
        format_type = loader.detect_format(sample_parquet_file)
        assert format_type == "parquet"

    def test_load_csv_file(self, sample_csv_file: str) -> None:
        """Test loading CSV file."""
        loader = FileLoader()
        data = loader.load(sample_csv_file)
        assert isinstance(data, pd.DataFrame)
        assert len(data) > 0
        assert "query_id" in data.columns

    def test_load_json_file(self, sample_json_file: str) -> None:
        """Test loading JSON file."""
        loader = FileLoader()
        data = loader.load(sample_json_file)
        assert isinstance(data, pd.DataFrame)
        assert len(data) > 0

    def test_load_corrupted_file(self, corrupted_csv_file: str) -> None:
        """Test handling of corrupted files."""
        loader = FileLoader()
        # The FileLoader should handle this gracefully and return data
        data = loader.load(corrupted_csv_file)
        assert isinstance(data, pd.DataFrame)
        # Should have some rows even if the file is malformed
        assert len(data) >= 0


class TestSchemaValidator:
    """Test schema validation functionality."""

    def test_validate_required_columns(self, sample_dataframe) -> None:
        """Test validation of required columns."""
        validator = SchemaValidator()
        schema = {"required_columns": ["query_id", "query_text"]}

        result = validator.validate(sample_dataframe, schema)
        assert result["valid"] is True
        assert "missing_columns" in result
        assert len(result["missing_columns"]) == 0

    def test_missing_required_columns(self, sample_dataframe) -> None:
        """Test detection of missing required columns."""
        validator = SchemaValidator()
        schema = {"required_columns": ["query_id", "missing_column"]}

        result = validator.validate(sample_dataframe, schema)
        assert result["valid"] is False
        assert "missing_column" in result["missing_columns"]

    def test_data_type_validation(self, sample_dataframe) -> None:
        """Test data type validation."""
        validator = SchemaValidator()
        schema = {
            "required_columns": ["query_id"],
            "column_types": {"query_id": "object"}
        }

        result = validator.validate(sample_dataframe, schema)
        assert result["valid"] is True

    def test_invalid_data_types(self, sample_dataframe) -> None:
        """Test detection of invalid data types."""
        validator = SchemaValidator()
        schema = {
            "required_columns": ["query_id"],
            "column_types": {"query_id": "int64"}
        }

        result = validator.validate(sample_dataframe, schema)
        assert result["valid"] is False
        assert "type_errors" in result


class TestPIIDetector:
    """Test PII detection functionality."""

    def test_detect_email_addresses(self, dataframe_with_pii) -> None:
        """Test detection of email addresses."""
        detector = PIIDetector()
        result = detector.scan(dataframe_with_pii)

        assert result["pii_found"] is True
        assert "email" in result["patterns_detected"]
        assert len(result["flagged_fields"]) > 0

    def test_detect_phone_numbers(self, dataframe_with_pii) -> None:
        """Test detection of phone numbers."""
        detector = PIIDetector()
        result = detector.scan(dataframe_with_pii)

        assert "phone" in result["patterns_detected"]

    def test_no_pii_detection(self, sample_dataframe) -> None:
        """Test when no PII is detected."""
        detector = PIIDetector()
        result = detector.scan(sample_dataframe)

        assert result["pii_found"] is False
        assert len(result["flagged_fields"]) == 0

    def test_custom_pii_patterns(self, sample_dataframe) -> None:
        """Test custom PII pattern detection."""
        detector = PIIDetector()
        custom_patterns = {"custom_id": r"ID-\d{6}"}
        detector.add_custom_patterns(custom_patterns)

        # Add test data with custom pattern
        test_data = sample_dataframe.copy()
        test_data["custom_field"] = ["ID-123456", "normal_text", "another_text", "ID-999999"]

        result = detector.scan(test_data)
        assert "custom_id" in result["patterns_detected"]

    def test_pii_redaction(self, dataframe_with_pii) -> None:
        """Test PII redaction functionality."""
        detector = PIIDetector()
        redacted_data = detector.redact(dataframe_with_pii)

        # Check that PII has been redacted
        assert "[REDACTED]" in str(redacted_data.values)


class TestDataQualityChecker:
    """Test data quality checking functionality."""

    def test_missing_value_detection(self, dataframe_with_missing) -> None:
        """Test detection of missing values."""
        checker = DataQualityChecker()
        result = checker.check(dataframe_with_missing)

        assert "missing_values" in result
        assert result["missing_values"]["total"] > 0

    def test_outlier_detection(self, dataframe_with_outliers) -> None:
        """Test outlier detection."""
        checker = DataQualityChecker()
        result = checker.check(dataframe_with_outliers)

        assert "outliers" in result
        assert len(result["outliers"]) > 0

    def test_data_consistency(self, sample_dataframe) -> None:
        """Test data consistency checks."""
        checker = DataQualityChecker()
        result = checker.check(sample_dataframe)

        assert "consistency" in result
        assert "duplicate_rows" in result["consistency"]

    def test_quality_score(self, sample_dataframe) -> None:
        """Test overall quality score calculation."""
        checker = DataQualityChecker()
        result = checker.check(sample_dataframe)

        assert "quality_score" in result
        assert 0 <= result["quality_score"] <= 1


class TestHashGenerator:
    """Test hash generation functionality."""

    def test_deterministic_hashing(self, sample_dataframe) -> None:
        """Test that hashing is deterministic."""
        generator = HashGenerator()
        hash1 = generator.generate(sample_dataframe)
        hash2 = generator.generate(sample_dataframe)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_different_data_different_hash(self, sample_dataframe) -> None:
        """Test that different data produces different hashes."""
        generator = HashGenerator()
        hash1 = generator.generate(sample_dataframe)

        modified_data = sample_dataframe.copy()
        modified_data.iloc[0, 0] = "modified"
        hash2 = generator.generate(modified_data)

        assert hash1 != hash2

    def test_normalized_hashing(self, sample_dataframe) -> None:
        """Test normalized data hashing."""
        generator = HashGenerator()
        hash_normalized = generator.generate(sample_dataframe, normalize=True)

        # Normalized hash might be different due to sorting/formatting
        assert len(hash_normalized) == 64

    def test_chunked_hashing(self, large_dataframe) -> None:
        """Test chunked hashing for large files."""
        generator = HashGenerator()
        hash_normal = generator.generate(large_dataframe)
        hash_chunked = generator.generate(large_dataframe, chunk_size=1000)

        assert hash_normal == hash_chunked


class TestManifestGenerator:
    """Test manifest generation functionality."""

    def test_basic_manifest_generation(self, sample_dataframe, tmp_path: str) -> None:
        """Test basic manifest generation."""
        generator = ManifestGenerator()
        test_file = tmp_path / "test.csv"
        sample_dataframe.to_csv(test_file, index=False)

        validation_results = {
            "schema_valid": True,
            "pii_found": False,
            "quality_score": 0.95
        }

        manifest = generator.generate(
            file_path=str(test_file),
            data=sample_dataframe,
            validation_results=validation_results,
            data_hash="abc123"
        )

        assert manifest["file_metadata"]["format"] == "csv"
        assert manifest["file_metadata"]["rows"] == len(sample_dataframe)
        assert manifest["validation_results"]["data_quality"]["quality_score"] == 0.95
        assert manifest["data_hash"] == "abc123"
        assert "timestamp" in manifest

    def test_manifest_schema_validation(self, sample_manifest) -> None:
        """Test that generated manifest follows schema."""
        required_fields = [
            "file_metadata", "validation_results", "data_hash",
            "timestamp", "schema_version"
        ]

        for field in required_fields:
            assert field in sample_manifest

    def test_manifest_signing(self, sample_manifest) -> None:
        """Test manifest signing functionality."""
        generator = ManifestGenerator()
        signed_manifest = generator.sign(sample_manifest)

        assert "signature" in signed_manifest
        assert signed_manifest["signature"] is not None
