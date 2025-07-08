"""Unit tests for constants module."""

import pytest
from src.utils.constants import (
    # Pipeline step names
    STEP_LOAD_BASELINE,
    STEP_INTEGRATE_DATA,
    STEP_TRAIN_MODEL,
    STEP_EVALUATE,
    STEP_COMPARE,
    STEP_ATTESTATION,
    STEP_MONITOR,
    # Model artifact names
    BASELINE_MODEL_NAME,
    NEW_MODEL_NAME,
    # Metric names
    METRIC_ACCURACY,
    METRIC_PRECISION,
    METRIC_RECALL,
    METRIC_F1,
    METRIC_AUROC,
    # Output formats
    OUTPUT_FORMAT_JSON,
    OUTPUT_FORMAT_PARQUET,
    OUTPUT_FORMAT_CSV,
    # File extensions
    SUPPORTED_DATA_FORMATS,
    # Attestation constants
    ATTESTATION_VERSION,
    ATTESTATION_SCHEMA_VERSION,
    # Status codes
    STATUS_SUCCESS,
    STATUS_FAILED,
    STATUS_PARTIAL,
    # Error messages
    ERROR_MODEL_NOT_FOUND,
    ERROR_DATA_VALIDATION,
    ERROR_METRIC_CALCULATION,
    # Logging formats
    LOG_FORMAT,
    LOG_DATE_FORMAT
)


class TestConstants:
    """Test suite for constants module."""

    def test_pipeline_step_names(self):
        """Test pipeline step name constants."""
        # Check all step names are defined
        assert STEP_LOAD_BASELINE == "load_baseline_model"
        assert STEP_INTEGRATE_DATA == "integrate_contributed_data"
        assert STEP_TRAIN_MODEL == "train_new_model"
        assert STEP_EVALUATE == "evaluate_on_benchmark"
        assert STEP_COMPARE == "compare_and_output_delta"
        assert STEP_ATTESTATION == "generate_attestation_output"
        assert STEP_MONITOR == "monitor_and_log"

        # Check they are all strings
        steps = [
            STEP_LOAD_BASELINE, STEP_INTEGRATE_DATA, STEP_TRAIN_MODEL,
            STEP_EVALUATE, STEP_COMPARE, STEP_ATTESTATION, STEP_MONITOR
        ]
        for step in steps:
            assert isinstance(step, str)
            assert len(step) > 0

    def test_model_artifact_names(self):
        """Test model artifact name constants."""
        assert BASELINE_MODEL_NAME == "baseline_model"
        assert NEW_MODEL_NAME == "new_model"

        # Ensure they are different
        assert BASELINE_MODEL_NAME != NEW_MODEL_NAME

    def test_metric_names(self):
        """Test metric name constants."""
        assert METRIC_ACCURACY == "accuracy"
        assert METRIC_PRECISION == "precision"
        assert METRIC_RECALL == "recall"
        assert METRIC_F1 == "f1_score"
        assert METRIC_AUROC == "auroc"

        # Check all are lowercase
        metrics = [
            METRIC_ACCURACY, METRIC_PRECISION, METRIC_RECALL,
            METRIC_F1, METRIC_AUROC
        ]
        for metric in metrics:
            assert metric.lower() == metric

    def test_output_formats(self):
        """Test output format constants."""
        assert OUTPUT_FORMAT_JSON == "json"
        assert OUTPUT_FORMAT_PARQUET == "parquet"
        assert OUTPUT_FORMAT_CSV == "csv"

        # Check they match common file extensions
        formats = [OUTPUT_FORMAT_JSON, OUTPUT_FORMAT_PARQUET, OUTPUT_FORMAT_CSV]
        for fmt in formats:
            assert fmt.lower() == fmt
            assert len(fmt) > 0

    def test_supported_data_formats(self):
        """Test supported data format extensions."""
        assert isinstance(SUPPORTED_DATA_FORMATS, list)
        assert len(SUPPORTED_DATA_FORMATS) > 0

        # Check expected formats
        assert ".json" in SUPPORTED_DATA_FORMATS
        assert ".csv" in SUPPORTED_DATA_FORMATS
        assert ".parquet" in SUPPORTED_DATA_FORMATS

        # Check all start with dot
        for fmt in SUPPORTED_DATA_FORMATS:
            assert fmt.startswith(".")
            assert len(fmt) > 1

    def test_attestation_constants(self):
        """Test attestation-related constants."""
        assert ATTESTATION_VERSION == "1.0"
        assert ATTESTATION_SCHEMA_VERSION == "1.0"

        # Check format
        for version in [ATTESTATION_VERSION, ATTESTATION_SCHEMA_VERSION]:
            assert isinstance(version, str)
            assert "." in version
            parts = version.split(".")
            assert len(parts) == 2
            assert parts[0].isdigit()
            assert parts[1].isdigit()

    def test_status_codes(self):
        """Test status code constants."""
        assert STATUS_SUCCESS == "success"
        assert STATUS_FAILED == "failed"
        assert STATUS_PARTIAL == "partial"

        # Check they are distinct
        statuses = [STATUS_SUCCESS, STATUS_FAILED, STATUS_PARTIAL]
        assert len(set(statuses)) == len(statuses)

        # Check all lowercase
        for status in statuses:
            assert status.lower() == status

    def test_error_messages(self):
        """Test error message templates."""
        assert ERROR_MODEL_NOT_FOUND == "Model not found: {}"
        assert ERROR_DATA_VALIDATION == "Data validation failed: {}"
        assert ERROR_METRIC_CALCULATION == "Metric calculation failed: {}"

        # Check they contain placeholders
        error_messages = [
            ERROR_MODEL_NOT_FOUND,
            ERROR_DATA_VALIDATION,
            ERROR_METRIC_CALCULATION
        ]
        for msg in error_messages:
            assert "{}" in msg
            assert msg.endswith(": {}")

        # Test formatting
        assert ERROR_MODEL_NOT_FOUND.format("test_model") == "Model not found: test_model"

    def test_logging_formats(self):
        """Test logging format constants."""
        assert isinstance(LOG_FORMAT, str)
        assert isinstance(LOG_DATE_FORMAT, str)

        # Check log format contains expected placeholders
        expected_placeholders = ["asctime", "name", "levelname", "message"]
        for placeholder in expected_placeholders:
            assert f"%({placeholder})s" in LOG_FORMAT

        # Check date format is valid
        import datetime
        now = datetime.datetime.now()
        formatted_date = now.strftime(LOG_DATE_FORMAT)
        assert len(formatted_date) > 0

    def test_constants_naming_convention(self):
        """Test that all constants follow UPPER_SNAKE_CASE convention."""
        import inspect
        import src.utils.constants as constants_module

        # Get all module attributes
        for name, value in inspect.getmembers(constants_module):
            # Skip private/magic attributes and imports
            if name.startswith("_") or inspect.ismodule(value):
                continue

            # Check naming convention
            assert name.isupper() or "_" in name
            assert name == name.upper()

    def test_constants_immutability(self):
        """Test that constants values are appropriate immutable types."""
        # String constants should not be mutable
        string_constants = [
            STEP_LOAD_BASELINE, BASELINE_MODEL_NAME, METRIC_ACCURACY,
            OUTPUT_FORMAT_JSON, STATUS_SUCCESS, LOG_FORMAT
        ]

        for const in string_constants:
            assert isinstance(const, str)

        # List constants
        assert isinstance(SUPPORTED_DATA_FORMATS, list)

        # Version constants should be strings
        assert isinstance(ATTESTATION_VERSION, str)
        assert isinstance(ATTESTATION_SCHEMA_VERSION, str)
