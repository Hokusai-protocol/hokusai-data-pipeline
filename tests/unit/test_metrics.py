"""Unit tests for metric logging convention functionality."""
import pytest
from unittest.mock import Mock, patch, call
import mlflow
from mlflow.exceptions import MlflowException

from src.utils.metrics import (
    MetricLogger,
    STANDARD_METRICS,
    MetricCategory,
    validate_metric_name,
    parse_metric_name,
    MetricValidationError
)


class TestMetricNaming:
    """Test metric naming conventions and validation."""

    def test_standard_metric_names(self):
        """Test that standard metrics follow naming conventions."""
        for metric_name in STANDARD_METRICS.keys():
            assert validate_metric_name(metric_name)
            category, name = parse_metric_name(metric_name)
            assert category in [c.value for c in MetricCategory]

    def test_valid_metric_names(self):
        """Test validation of valid metric names."""
        valid_names = [
            "reply_rate",
            "usage:reply_rate",
            "model:accuracy",
            "pipeline:processing_time",
            "custom:user_engagement",
            "usage:reply_rate.v2",
            "model:f1_score_weighted"
        ]

        for name in valid_names:
            assert validate_metric_name(name)

    def test_invalid_metric_names(self):
        """Test validation rejects invalid metric names."""
        invalid_names = [
            "",
            "metric with spaces",
            "metric:with:too:many:colons",
            "UPPERCASE_METRIC",
            "metric-with-dashes",
            "metric@special",
            ":no_category",
            "category:",
            "123_starts_with_number"
        ]

        for name in invalid_names:
            assert not validate_metric_name(name)

    def test_parse_metric_name(self):
        """Test parsing metric names into category and name."""
        test_cases = [
            ("usage:reply_rate", ("usage", "reply_rate")),
            ("model:accuracy", ("model", "accuracy")),
            ("reply_rate", (None, "reply_rate")),
            ("custom:metric.v2", ("custom", "metric.v2"))
        ]

        for metric_name, expected in test_cases:
            assert parse_metric_name(metric_name) == expected


class TestMetricLogger:
    """Test MetricLogger functionality."""

    @pytest.fixture
    def mock_mlflow(self):
        """Mock MLflow for testing."""
        with patch("src.utils.metrics.mlflow") as mock:
            yield mock

    @pytest.fixture
    def logger(self, mock_mlflow):
        """Create MetricLogger instance."""
        return MetricLogger()

    def test_log_metric_simple(self, logger, mock_mlflow):
        """Test simple metric logging."""
        logger.log_metric("reply_rate", 0.1523)

        mock_mlflow.log_metric.assert_called_once_with("reply_rate", 0.1523)

    def test_log_metric_with_prefix(self, logger, mock_mlflow):
        """Test metric logging with category prefix."""
        logger.log_metric("usage:reply_rate", 0.1523)

        mock_mlflow.log_metric.assert_called_once_with("usage:reply_rate", 0.1523)

    def test_log_metric_validation(self, logger):
        """Test metric name validation during logging."""
        with pytest.raises(MetricValidationError):
            logger.log_metric("invalid metric name", 0.5, raise_on_error=True)

    def test_log_metrics_batch(self, logger, mock_mlflow):
        """Test batch metric logging."""
        metrics = {
            "usage:reply_rate": 0.1523,
            "usage:conversion_rate": 0.0821,
            "model:accuracy": 0.8934
        }

        logger.log_metrics(metrics)

        expected_calls = [
            call(name, value) for name, value in metrics.items()
        ]
        mock_mlflow.log_metric.assert_has_calls(expected_calls, any_order=True)

    def test_log_metrics_validation(self, logger):
        """Test batch logging validates all metric names."""
        metrics = {
            "valid_metric": 0.5,
            "invalid metric": 0.3
        }

        with pytest.raises(MetricValidationError):
            logger.log_metrics(metrics, raise_on_error=True)

    def test_log_metric_with_metadata(self, logger, mock_mlflow):
        """Test metric logging with metadata."""
        metadata = {
            "model_version": "2.0.1",
            "experiment": "baseline_comparison"
        }

        logger.log_metric_with_metadata(
            "usage:reply_rate",
            0.1523,
            metadata
        )

        # Should log metric
        mock_mlflow.log_metric.assert_called_with("usage:reply_rate", 0.1523)

        # Should log metadata as params
        expected_param_calls = [
            call("metric_metadata.usage:reply_rate.model_version", "2.0.1"),
            call("metric_metadata.usage:reply_rate.experiment", "baseline_comparison")
        ]
        mock_mlflow.log_param.assert_has_calls(expected_param_calls, any_order=True)

    def test_log_metric_error_handling(self, logger, mock_mlflow):
        """Test error handling during metric logging."""
        mock_mlflow.log_metric.side_effect = MlflowException("MLflow error")

        # Should not raise, but log warning
        with patch("src.utils.metrics.logger") as mock_logger:
            logger.log_metric("valid_metric", 0.5, raise_on_error=False)
            mock_logger.warning.assert_called()

    def test_log_metric_error_raising(self, logger, mock_mlflow):
        """Test error raising during metric logging."""
        mock_mlflow.log_metric.side_effect = MlflowException("MLflow error")

        with pytest.raises(MlflowException):
            logger.log_metric("valid_metric", 0.5, raise_on_error=True)

    def test_get_metrics_by_prefix(self, logger, mock_mlflow):
        """Test retrieving metrics by prefix."""
        mock_run = Mock()
        mock_run.data.metrics = {
            "usage:reply_rate": 0.15,
            "usage:conversion_rate": 0.08,
            "model:accuracy": 0.89,
            "custom:metric": 0.5
        }
        mock_mlflow.get_run.return_value = mock_run

        usage_metrics = logger.get_metrics_by_prefix("run_id", "usage:")

        assert len(usage_metrics) == 2
        assert "usage:reply_rate" in usage_metrics
        assert "usage:conversion_rate" in usage_metrics
        assert usage_metrics["usage:reply_rate"] == 0.15

    def test_aggregate_metrics(self, logger):
        """Test metric aggregation functionality."""
        metrics_list = [
            {"reply_rate": 0.15, "accuracy": 0.85},
            {"reply_rate": 0.18, "accuracy": 0.87},
            {"reply_rate": 0.12, "accuracy": 0.83}
        ]

        aggregated = logger.aggregate_metrics(metrics_list)

        assert aggregated["reply_rate"]["mean"] == pytest.approx(0.15, rel=1e-3)
        assert aggregated["reply_rate"]["min"] == 0.12
        assert aggregated["reply_rate"]["max"] == 0.18
        assert aggregated["accuracy"]["mean"] == pytest.approx(0.85, rel=1e-3)


class TestMetricCategories:
    """Test metric category functionality."""

    def test_category_enum_values(self):
        """Test MetricCategory enum has expected values."""
        assert MetricCategory.USAGE.value == "usage"
        assert MetricCategory.MODEL.value == "model"
        assert MetricCategory.PIPELINE.value == "pipeline"
        assert MetricCategory.CUSTOM.value == "custom"

    def test_get_category_metrics(self):
        """Test getting all metrics for a category."""
        usage_metrics = [
            name for name in STANDARD_METRICS.keys()
            if name.startswith("usage:")
        ]

        assert len(usage_metrics) > 0
        assert all(name.startswith("usage:") for name in usage_metrics)


class TestMetricUtilities:
    """Test metric utility functions."""

    def test_format_metric_name(self):
        """Test metric name formatting."""
        from src.utils.metrics import format_metric_name

        assert format_metric_name("usage", "reply_rate") == "usage:reply_rate"
        assert format_metric_name(None, "reply_rate") == "reply_rate"
        assert format_metric_name("model", "f1_score") == "model:f1_score"

    def test_metric_value_validation(self):
        """Test metric value validation."""
        from src.utils.metrics import validate_metric_value

        # Valid values
        assert validate_metric_value(0.5)
        assert validate_metric_value(100)
        assert validate_metric_value(0)
        assert validate_metric_value(-0.5)  # Some metrics can be negative

        # Invalid values
        assert not validate_metric_value("not a number")
        assert not validate_metric_value(None)
        assert not validate_metric_value([1, 2, 3])
        assert not validate_metric_value(float("inf"))
        assert not validate_metric_value(float("nan"))


class TestIntegrationWithPipeline:
    """Test integration with existing pipeline."""

    @patch("src.utils.metrics.mlflow")
    def test_pipeline_metric_logging(self, mock_mlflow):
        """Test that pipeline uses standardized metric logging."""
        from src.utils.metrics import log_pipeline_metrics

        # Simulate pipeline metrics
        pipeline_metrics = {
            "data_processed": 1000,
            "success_rate": 0.95,
            "duration_seconds": 120.5
        }

        log_pipeline_metrics(pipeline_metrics)

        # Verify metrics logged with proper prefixes
        expected_calls = [
            call("pipeline:data_processed", 1000),
            call("pipeline:success_rate", 0.95),
            call("pipeline:duration_seconds", 120.5)
        ]
        mock_mlflow.log_metric.assert_has_calls(expected_calls, any_order=True)


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    @patch("src.utils.metrics.mlflow")
    def test_legacy_metric_logging(self, mock_mlflow):
        """Test that legacy metric names still work."""
        from src.utils.metrics import MetricLogger

        logger = MetricLogger(allow_legacy_names=True)

        # Legacy names without validation
        logger.log_metric("some-legacy-metric", 0.5)
        mock_mlflow.log_metric.assert_called_with("some-legacy-metric", 0.5)

    def test_migration_helper(self):
        """Test metric name migration helper."""
        from src.utils.metrics import migrate_metric_name

        migrations = {
            "accuracy": "model:accuracy",
            "f1_score": "model:f1_score",
            "reply_rate": "usage:reply_rate",
            "processing_time": "pipeline:duration_seconds"
        }

        for old_name, expected_new in migrations.items():
            assert migrate_metric_name(old_name) == expected_new
