"""Standardized metric logging utilities for Hokusai platform.

This module provides a consistent interface for logging metrics to MLflow,
with support for metric categorization, validation, and organization.
"""
import re
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Union
from statistics import mean, median
import mlflow
from mlflow.exceptions import MlflowException

logger = logging.getLogger(__name__)


class MetricCategory(Enum):
    """Categories for organizing metrics."""

    USAGE = "usage"
    MODEL = "model"
    PIPELINE = "pipeline"
    CUSTOM = "custom"


# Standard metric definitions with descriptions
STANDARD_METRICS = {
    # Usage metrics - track how models/features are being used
    "usage:reply_rate": "Rate of replies to messages",
    "usage:conversion_rate": "Conversion rate for actions",
    "usage:engagement_rate": "User engagement rate",
    "usage:click_through_rate": "Click-through rate",
    "usage:retention_rate": "User retention rate",

    # Model metrics - track model performance
    "model:accuracy": "Model accuracy score",
    "model:precision": "Model precision score",
    "model:recall": "Model recall score",
    "model:f1_score": "F1 score",
    "model:auroc": "Area under ROC curve",
    "model:latency_ms": "Inference latency in milliseconds",
    "model:throughput_qps": "Queries per second",

    # Pipeline metrics - track pipeline execution
    "pipeline:data_processed": "Amount of data processed",
    "pipeline:success_rate": "Pipeline success rate",
    "pipeline:duration_seconds": "Pipeline execution time",
    "pipeline:memory_usage_mb": "Memory usage in megabytes",
    "pipeline:error_rate": "Pipeline error rate",

    # Custom metrics placeholder
    "custom:metric": "Custom metric (user-defined)"
}

# Regex pattern for valid metric names
METRIC_NAME_PATTERN = re.compile(r"^([a-z]+:)?[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")


class MetricValidationError(Exception):
    """Raised when metric validation fails."""

    pass


def validate_metric_name(name: str) -> bool:
    """Validate metric name against naming conventions.
    
    Args:
        name: Metric name to validate
        
    Returns:
        True if valid, False otherwise

    """
    if not name:
        return False
    return bool(METRIC_NAME_PATTERN.match(name))


def parse_metric_name(name: str) -> Tuple[Optional[str], str]:
    """Parse metric name into category and base name.
    
    Args:
        name: Full metric name (e.g., "usage:reply_rate")
        
    Returns:
        Tuple of (category, base_name) or (None, name) if no category

    """
    if ":" in name:
        parts = name.split(":", 1)
        return parts[0], parts[1]
    return None, name


def format_metric_name(category: Optional[str], name: str) -> str:
    """Format metric name with optional category prefix.
    
    Args:
        category: Optional category prefix
        name: Base metric name
        
    Returns:
        Formatted metric name

    """
    if category:
        return f"{category}:{name}"
    return name


def validate_metric_value(value: Any) -> bool:
    """Validate metric value is numeric and finite.
    
    Args:
        value: Value to validate
        
    Returns:
        True if valid, False otherwise

    """
    if not isinstance(value, (int, float)):
        return False

    if isinstance(value, float):
        if not (-float("inf") < value < float("inf")):
            return False
        if value != value:  # NaN check
            return False

    return True


def migrate_metric_name(old_name: str) -> str:
    """Migrate legacy metric name to new convention.
    
    Args:
        old_name: Legacy metric name
        
    Returns:
        New standardized metric name

    """
    # Common migrations
    migrations = {
        "accuracy": "model:accuracy",
        "precision": "model:precision",
        "recall": "model:recall",
        "f1_score": "model:f1_score",
        "f1": "model:f1_score",
        "auc": "model:auroc",
        "auroc": "model:auroc",
        "reply_rate": "usage:reply_rate",
        "conversion_rate": "usage:conversion_rate",
        "processing_time": "pipeline:duration_seconds",
        "duration": "pipeline:duration_seconds",
        "latency": "model:latency_ms"
    }

    return migrations.get(old_name, old_name)


class MetricLogger:
    """Centralized metric logging with MLflow integration."""

    def __init__(self, allow_legacy_names: bool = False):
        """Initialize MetricLogger.
        
        Args:
            allow_legacy_names: Whether to allow non-standard metric names

        """
        self.allow_legacy_names = allow_legacy_names

    def log_metric(
        self,
        name: str,
        value: float,
        step: Optional[int] = None,
        raise_on_error: bool = True
    ) -> None:
        """Log a single metric to MLflow.
        
        Args:
            name: Metric name (following naming conventions)
            value: Metric value
            step: Optional step/iteration number
            raise_on_error: Whether to raise exceptions or log warnings
            
        Raises:
            MetricValidationError: If validation fails and raise_on_error=True

        """
        # Validate metric name
        if not self.allow_legacy_names and not validate_metric_name(name):
            error_msg = f"Invalid metric name: {name}"
            if raise_on_error:
                raise MetricValidationError(error_msg)
            logger.warning(error_msg)
            return

        # Validate metric value
        if not validate_metric_value(value):
            error_msg = f"Invalid metric value for {name}: {value}"
            if raise_on_error:
                raise MetricValidationError(error_msg)
            logger.warning(error_msg)
            return

        try:
            if step is not None:
                mlflow.log_metric(name, value, step=step)
            else:
                mlflow.log_metric(name, value)
            logger.debug(f"Logged metric {name}={value}")
        except MlflowException as e:
            error_msg = f"Failed to log metric {name}: {e}"
            if raise_on_error:
                raise
            logger.warning(error_msg)

    def log_metrics(
        self,
        metrics: Dict[str, float],
        step: Optional[int] = None,
        raise_on_error: bool = True
    ) -> None:
        """Log multiple metrics in batch.
        
        Args:
            metrics: Dictionary of metric name to value
            step: Optional step/iteration number
            raise_on_error: Whether to raise exceptions or log warnings

        """
        # Validate all metrics first
        for name, value in metrics.items():
            if not self.allow_legacy_names and not validate_metric_name(name):
                error_msg = f"Invalid metric name in batch: {name}"
                if raise_on_error:
                    raise MetricValidationError(error_msg)
                logger.warning(error_msg)
                continue

            if not validate_metric_value(value):
                error_msg = f"Invalid metric value in batch for {name}: {value}"
                if raise_on_error:
                    raise MetricValidationError(error_msg)
                logger.warning(error_msg)
                continue

        # Log all valid metrics
        for name, value in metrics.items():
            if (self.allow_legacy_names or validate_metric_name(name)) and validate_metric_value(value):
                self.log_metric(name, value, step, raise_on_error=False)

    def log_metric_with_metadata(
        self,
        name: str,
        value: float,
        metadata: Dict[str, Any],
        step: Optional[int] = None
    ) -> None:
        """Log metric with additional metadata as MLflow parameters.
        
        Args:
            name: Metric name
            value: Metric value
            metadata: Additional metadata to log as parameters
            step: Optional step/iteration number

        """
        # Log the metric
        self.log_metric(name, value, step)

        # Log metadata as parameters
        for key, val in metadata.items():
            param_name = f"metric_metadata.{name}.{key}"
            try:
                mlflow.log_param(param_name, str(val))
            except MlflowException as e:
                logger.warning(f"Failed to log metadata for {name}: {e}")

    def get_metrics_by_prefix(
        self,
        run_id: str,
        prefix: str
    ) -> Dict[str, float]:
        """Get all metrics with a given prefix from a run.
        
        Args:
            run_id: MLflow run ID
            prefix: Metric name prefix (e.g., "usage:")
            
        Returns:
            Dictionary of matching metrics

        """
        try:
            run = mlflow.get_run(run_id)
            metrics = run.data.metrics

            return {
                name: value
                for name, value in metrics.items()
                if name.startswith(prefix)
            }
        except MlflowException as e:
            logger.error(f"Failed to get metrics for run {run_id}: {e}")
            return {}

    def aggregate_metrics(
        self,
        metrics_list: List[Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """Aggregate metrics across multiple runs.
        
        Args:
            metrics_list: List of metric dictionaries from different runs
            
        Returns:
            Aggregated metrics with mean, min, max, median

        """
        aggregated = {}

        # Collect all unique metric names
        all_metrics = set()
        for metrics in metrics_list:
            all_metrics.update(metrics.keys())

        # Aggregate each metric
        for metric_name in all_metrics:
            values = [
                metrics.get(metric_name)
                for metrics in metrics_list
                if metric_name in metrics
            ]

            if values:
                aggregated[metric_name] = {
                    "mean": mean(values),
                    "min": min(values),
                    "max": max(values),
                    "median": median(values),
                    "count": len(values)
                }

        return aggregated


# Convenience functions for common use cases
def log_usage_metrics(metrics: Dict[str, float], **kwargs) -> None:
    """Log usage metrics with automatic prefixing."""
    logger = MetricLogger()
    prefixed_metrics = {
        format_metric_name("usage", name): value
        for name, value in metrics.items()
    }
    logger.log_metrics(prefixed_metrics, **kwargs)


def log_model_metrics(metrics: Dict[str, float], **kwargs) -> None:
    """Log model performance metrics with automatic prefixing."""
    logger = MetricLogger()
    prefixed_metrics = {
        format_metric_name("model", name): value
        for name, value in metrics.items()
    }
    logger.log_metrics(prefixed_metrics, **kwargs)


def log_pipeline_metrics(metrics: Dict[str, float], **kwargs) -> None:
    """Log pipeline execution metrics with automatic prefixing."""
    logger = MetricLogger()
    prefixed_metrics = {
        format_metric_name("pipeline", name): value
        for name, value in metrics.items()
    }
    logger.log_metrics(prefixed_metrics, **kwargs)


# Global logger instance for backward compatibility
_global_logger = MetricLogger()

# Expose main functions at module level
log_metric = _global_logger.log_metric
log_metrics = _global_logger.log_metrics
log_metric_with_metadata = _global_logger.log_metric_with_metadata
