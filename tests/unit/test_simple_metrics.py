"""Simple unit tests for metrics utilities."""

from unittest.mock import patch

from src.utils.metrics import (
    METRIC_NAME_PATTERN,
    STANDARD_METRICS,
    MetricCategory,
    format_metric_name,
    log_model_metrics,
    log_pipeline_metrics,
    log_usage_metrics,
    migrate_metric_name,
    parse_metric_name,
    validate_metric_name,
    validate_metric_value,
)


class TestMetricCategory:
    """Test suite for MetricCategory enum."""

    def test_metric_categories(self):
        """Test metric category values."""
        assert MetricCategory.USAGE.value == "usage"
        assert MetricCategory.MODEL.value == "model"
        assert MetricCategory.PIPELINE.value == "pipeline"
        assert MetricCategory.CUSTOM.value == "custom"


class TestMetricValidation:
    """Test suite for metric validation functions."""

    def test_validate_metric_name_valid(self):
        """Test validation of valid metric names."""
        valid_names = [
            "accuracy",
            "model:accuracy",
            "usage:reply_rate",
            "custom:user_score",
            "pipeline:duration_seconds",
            "model:latency_ms",
            "metric.with.dots",
            "category:metric.with.dots",
        ]

        for name in valid_names:
            assert validate_metric_name(name) is True

    def test_validate_metric_name_invalid(self):
        """Test validation of invalid metric names."""
        invalid_names = [
            "",
            "UPPERCASE",
            "CamelCase",
            "with-dashes",
            "with spaces",
            "123starts_with_number",
            ":missing_category",
            "category:",
            "special@chars",
            "category:UPPERCASE",
        ]

        for name in invalid_names:
            assert validate_metric_name(name) is False

    def test_parse_metric_name(self):
        """Test parsing metric names into category and base name."""
        # With category
        category, name = parse_metric_name("model:accuracy")
        assert category == "model"
        assert name == "accuracy"

        # Without category
        category, name = parse_metric_name("accuracy")
        assert category is None
        assert name == "accuracy"

        # With dots
        category, name = parse_metric_name("custom:user.engagement.rate")
        assert category == "custom"
        assert name == "user.engagement.rate"

    def test_format_metric_name(self):
        """Test formatting metric names with categories."""
        # Add category
        assert format_metric_name("model", "accuracy") == "model:accuracy"

        # No category provided
        assert format_metric_name(None, "accuracy") == "accuracy"

        # Empty category
        assert format_metric_name("", "accuracy") == "accuracy"


class TestMetricUtilities:
    """Test suite for metric utility functions."""

    def test_validate_metric_value(self):
        """Test metric value validation."""
        # Valid values
        assert validate_metric_value(0.95) is True
        assert validate_metric_value(100) is True
        assert validate_metric_value(-0.5) is True
        assert validate_metric_value(0) is True

        # Invalid values
        assert validate_metric_value(None) is False
        assert validate_metric_value("string") is False
        assert validate_metric_value([1, 2, 3]) is False
        assert validate_metric_value(float("inf")) is False
        assert validate_metric_value(float("nan")) is False

    def test_migrate_metric_name(self):
        """Test metric name migration."""
        # Test various old formats
        assert migrate_metric_name("accuracy") == "model:accuracy"
        assert migrate_metric_name("reply_rate") == "usage:reply_rate"
        assert migrate_metric_name("latency") == "model:latency_ms"
        assert migrate_metric_name("duration") == "pipeline:duration_seconds"

        # Unknown names should not change
        assert migrate_metric_name("unknown_metric") == "unknown_metric"
        
        # Already migrated names should not change
        assert migrate_metric_name("model:accuracy") == "model:accuracy"
        assert migrate_metric_name("usage:reply_rate") == "usage:reply_rate"


class TestCategorizedMetricLogging:
    """Test suite for category-specific metric logging."""

    @patch("mlflow.log_metric")
    def test_log_usage_metrics(self, mock_log_metric):
        """Test logging usage metrics."""
        metrics = {"reply_rate": 0.75, "engagement_rate": 0.85}

        log_usage_metrics(metrics)

        # MLflow will receive names with underscores instead of colons
        assert mock_log_metric.call_count == 2
        calls = mock_log_metric.call_args_list
        logged_metrics = {call[0][0]: call[0][1] for call in calls}
        assert logged_metrics == {"usage_reply_rate": 0.75, "usage_engagement_rate": 0.85}

    @patch("mlflow.log_metric")
    def test_log_model_metrics(self, mock_log_metric):
        """Test logging model metrics."""
        metrics = {"accuracy": 0.95, "latency_ms": 45.2}

        log_model_metrics(metrics)

        # MLflow will receive names with underscores instead of colons
        assert mock_log_metric.call_count == 2
        calls = mock_log_metric.call_args_list
        logged_metrics = {call[0][0]: call[0][1] for call in calls}
        assert logged_metrics == {"model_accuracy": 0.95, "model_latency_ms": 45.2}

    @patch("mlflow.log_metric")
    def test_log_pipeline_metrics(self, mock_log_metric):
        """Test logging pipeline metrics."""
        metrics = {"duration_seconds": 120.5, "success_rate": 0.98}

        log_pipeline_metrics(metrics)

        # MLflow will receive names with underscores instead of colons
        assert mock_log_metric.call_count == 2
        calls = mock_log_metric.call_args_list
        logged_metrics = {call[0][0]: call[0][1] for call in calls}
        assert logged_metrics == {"pipeline_duration_seconds": 120.5, "pipeline_success_rate": 0.98}

    @patch("mlflow.log_metric")
    def test_log_metrics_with_existing_prefix(self, mock_log_metric):
        """Test that existing prefixes are preserved."""
        metrics = {"accuracy": 0.95, "model:precision": 0.92}  # Already has prefix

        log_model_metrics(metrics)

        # MLflow will receive names with underscores instead of colons
        assert mock_log_metric.call_count == 2
        calls = mock_log_metric.call_args_list
        logged_metrics = {call[0][0]: call[0][1] for call in calls}
        # Metrics with existing prefix are preserved (no double prefix)
        assert logged_metrics == {"model_accuracy": 0.95, "model_precision": 0.92}


class TestStandardMetrics:
    """Test suite for standard metrics definitions."""

    def test_standard_metrics_defined(self):
        """Test that standard metrics are properly defined."""
        assert len(STANDARD_METRICS) > 0

        # Check categories are represented
        categories = set()
        for metric_name in STANDARD_METRICS:
            if ":" in metric_name:
                category = metric_name.split(":")[0]
                categories.add(category)

        assert "usage" in categories
        assert "model" in categories
        assert "pipeline" in categories

    def test_standard_metrics_valid(self):
        """Test that all standard metrics have valid names."""
        for metric_name in STANDARD_METRICS:
            assert validate_metric_name(metric_name) is True

    def test_metric_name_pattern(self):
        """Test the metric name regex pattern."""
        # Valid patterns
        assert METRIC_NAME_PATTERN.match("metric")
        assert METRIC_NAME_PATTERN.match("category:metric")
        assert METRIC_NAME_PATTERN.match("my_metric_123")
        assert METRIC_NAME_PATTERN.match("category:metric.sub.value")

        # Invalid patterns
        assert not METRIC_NAME_PATTERN.match("UPPERCASE")
        assert not METRIC_NAME_PATTERN.match("123metric")
        assert not METRIC_NAME_PATTERN.match("metric-with-dash")
        assert not METRIC_NAME_PATTERN.match("metric with space")
