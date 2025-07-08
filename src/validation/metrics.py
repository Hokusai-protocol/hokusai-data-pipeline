"""Metric validation module for Hokusai ML Platform.
"""
import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SupportedMetrics(Enum):
    """Enumeration of supported metrics."""

    # Classification metrics
    ACCURACY = "accuracy"
    AUROC = "auroc"
    AUC = "auc"
    F1 = "f1"
    PRECISION = "precision"
    RECALL = "recall"

    # Regression metrics
    MSE = "mse"
    RMSE = "rmse"
    MAE = "mae"
    R2 = "r2"

    # Custom metrics
    REPLY_RATE = "reply_rate"
    CONVERSION_RATE = "conversion_rate"
    ENGAGEMENT_SCORE = "engagement_score"

    @classmethod
    def get_all_names(cls) -> set[str]:
        """Get all metric names as a set."""
        return {metric.value for metric in cls}

    @classmethod
    def is_valid(cls, metric_name: str) -> bool:
        """Check if a metric name is valid."""
        return metric_name.lower() in cls.get_all_names()

    @classmethod
    def get_metric_type(cls, metric_name: str) -> str:
        """Get the type of metric (classification, regression, custom)."""
        classification_metrics = {
            cls.ACCURACY.value,
            cls.AUROC.value,
            cls.AUC.value,
            cls.F1.value,
            cls.PRECISION.value,
            cls.RECALL.value,
        }
        regression_metrics = {cls.MSE.value, cls.RMSE.value, cls.MAE.value, cls.R2.value}

        metric_lower = metric_name.lower()
        if metric_lower in classification_metrics:
            return "classification"
        elif metric_lower in regression_metrics:
            return "regression"
        else:
            return "custom"


class MetricValidator:
    """Validates metrics and their values."""

    def __init__(self) -> None:
        self.metric_ranges = self._get_metric_ranges()

    def _get_metric_ranges(self) -> dict[str, dict[str, Any]]:
        """Define valid ranges for each metric."""
        return {
            # Classification metrics (0-1 range)
            SupportedMetrics.ACCURACY.value: {"min": 0.0, "max": 1.0},
            SupportedMetrics.AUROC.value: {"min": 0.0, "max": 1.0},
            SupportedMetrics.AUC.value: {"min": 0.0, "max": 1.0},
            SupportedMetrics.F1.value: {"min": 0.0, "max": 1.0},
            SupportedMetrics.PRECISION.value: {"min": 0.0, "max": 1.0},
            SupportedMetrics.RECALL.value: {"min": 0.0, "max": 1.0},
            # Regression metrics (no upper bound)
            SupportedMetrics.MSE.value: {"min": 0.0, "max": None},
            SupportedMetrics.RMSE.value: {"min": 0.0, "max": None},
            SupportedMetrics.MAE.value: {"min": 0.0, "max": None},
            SupportedMetrics.R2.value: {"min": None, "max": 1.0},  # Can be negative
            # Custom metrics
            SupportedMetrics.REPLY_RATE.value: {"min": 0.0, "max": 1.0},
            SupportedMetrics.CONVERSION_RATE.value: {"min": 0.0, "max": 1.0},
            SupportedMetrics.ENGAGEMENT_SCORE.value: {"min": 0.0, "max": None},
        }

    def validate_metric_name(self, metric_name: str) -> bool:
        """Validate if a metric name is supported."""
        is_valid = SupportedMetrics.is_valid(metric_name)
        if not is_valid:
            logger.warning(f"Unsupported metric: {metric_name}")
            logger.info(f"Supported metrics: {', '.join(SupportedMetrics.get_all_names())}")
        return is_valid

    def validate_metric_value(self, metric_name: str, value: float) -> bool:
        """Validate if a metric value is within expected range."""
        if not self.validate_metric_name(metric_name):
            return False

        metric_range = self.metric_ranges.get(metric_name.lower())
        if not metric_range:
            logger.warning(f"No range defined for metric: {metric_name}")
            return True  # Allow if no range is defined

        min_val = metric_range.get("min")
        max_val = metric_range.get("max")

        if min_val is not None and value < min_val:
            logger.error(f"Metric {metric_name} value {value} is below minimum {min_val}")
            return False

        if max_val is not None and value > max_val:
            logger.error(f"Metric {metric_name} value {value} is above maximum {max_val}")
            return False

        return True

    def validate_baseline(self, metric_name: str, baseline: float) -> bool:
        """Validate if a baseline value is reasonable for the metric."""
        if not self.validate_metric_value(metric_name, baseline):
            return False

        # Additional baseline-specific validation
        metric_type = SupportedMetrics.get_metric_type(metric_name)

        if metric_type == "classification":
            # For classification metrics, warn if baseline is too low or too high
            if baseline < 0.1:
                logger.warning(f"Baseline {baseline} for {metric_name} seems unusually low")
            elif baseline > 0.99:
                logger.warning(f"Baseline {baseline} for {metric_name} seems unusually high")

        elif metric_type == "regression" and metric_name.lower() != "r2":
            # For error metrics, baseline should be positive
            if baseline <= 0:
                logger.error(f"Baseline for error metric {metric_name} must be positive")
                return False

        return True

    def calculate_metric(self, metric_name: str, predictions: Any, targets: Any) -> Optional[float]:
        """Calculate actual metric value from predictions and targets."""
        # This would integrate with actual ML libraries like scikit-learn
        # For now, it's a placeholder that would be implemented based on requirements
        logger.info(f"Calculating {metric_name} metric")

        # Placeholder implementation
        # In real implementation, this would use:
        # - sklearn.metrics for standard metrics
        # - Custom implementations for business metrics

        return None
