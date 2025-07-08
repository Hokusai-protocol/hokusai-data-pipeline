"""Baseline comparison module for Hokusai ML Platform."""

import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ComparisonResult(Enum):
    """Result of baseline comparison."""

    IMPROVED = "improved"
    NO_CHANGE = "no_change"
    DEGRADED = "degraded"


class BaselineComparator:
    """Compares model performance against baseline."""

    def __init__(self, tolerance: float = 1e-6) -> None:
        """Initialize comparator with optional tolerance for floating point comparison.

        Args:
            tolerance: Small value to handle floating point comparison

        """
        self.tolerance = tolerance

    def compare(
        self, current_value: float, baseline_value: float, metric_type: str = "higher_better"
    ) -> ComparisonResult:
        """Compare current metric value against baseline.

        Args:
            current_value: Current model's metric value
            baseline_value: Baseline metric value to compare against
            metric_type: Either "higher_better" (accuracy, AUC) or "lower_better" (MSE, MAE)

        Returns:
            ComparisonResult indicating if model improved, degraded, or stayed same

        """
        if abs(current_value - baseline_value) < self.tolerance:
            return ComparisonResult.NO_CHANGE

        if metric_type == "higher_better":
            if current_value > baseline_value:
                return ComparisonResult.IMPROVED
            else:
                return ComparisonResult.DEGRADED
        elif metric_type == "lower_better":
            if current_value < baseline_value:
                return ComparisonResult.IMPROVED
            else:
                return ComparisonResult.DEGRADED
        else:
            raise ValueError(f"Unknown metric type: {metric_type}")

    def meets_threshold(
        self,
        current_value: float,
        baseline_value: float,
        threshold: float,
        metric_type: str = "higher_better",
    ) -> bool:
        """Check if current value meets or exceeds threshold requirement.

        Args:
            current_value: Current model's metric value
            baseline_value: Baseline metric value
            threshold: Minimum improvement required (absolute or percentage)
            metric_type: Either "higher_better" or "lower_better"

        Returns:
            True if threshold is met, False otherwise

        """
        if metric_type == "higher_better":
            return current_value >= baseline_value + threshold
        elif metric_type == "lower_better":
            return current_value <= baseline_value - threshold
        else:
            raise ValueError(f"Unknown metric type: {metric_type}")

    def calculate_improvement(
        self, current_value: float, baseline_value: float, as_percentage: bool = False
    ) -> float:
        """Calculate improvement over baseline.

        Args:
            current_value: Current model's metric value
            baseline_value: Baseline metric value
            as_percentage: If True, return as percentage improvement

        Returns:
            Improvement value (positive means better, negative means worse)

        """
        improvement = current_value - baseline_value

        if as_percentage and baseline_value != 0:
            improvement = (improvement / abs(baseline_value)) * 100

        return improvement

    def get_metric_type(self, metric_name: str) -> str:
        """Determine if metric is "higher_better" or "lower_better".

        Args:
            metric_name: Name of the metric

        Returns:
            "higher_better" or "lower_better"

        """
        lower_better_metrics = {"mse", "rmse", "mae", "error", "loss"}

        if any(term in metric_name.lower() for term in lower_better_metrics):
            return "lower_better"
        else:
            return "higher_better"

    def validate_improvement(
        self,
        current_value: float,
        baseline_value: float,
        metric_name: str,
        required_improvement: Optional[float] = None,
    ) -> dict[str, Any]:
        """Comprehensive validation of model improvement.

        Args:
            current_value: Current model's metric value
            baseline_value: Baseline metric value
            metric_name: Name of the metric being compared
            required_improvement: Optional minimum improvement required

        Returns:
            Dictionary with validation results

        """
        metric_type = self.get_metric_type(metric_name)
        comparison = self.compare(current_value, baseline_value, metric_type)
        improvement = self.calculate_improvement(current_value, baseline_value)
        improvement_pct = self.calculate_improvement(
            current_value, baseline_value, as_percentage=True
        )

        result = {
            "metric_name": metric_name,
            "current_value": current_value,
            "baseline_value": baseline_value,
            "comparison": comparison.value,
            "improvement": improvement,
            "improvement_percentage": improvement_pct,
            "meets_baseline": comparison != ComparisonResult.DEGRADED,
        }

        if required_improvement is not None:
            meets_threshold = self.meets_threshold(
                current_value, baseline_value, required_improvement, metric_type
            )
            result["required_improvement"] = required_improvement
            result["meets_threshold"] = meets_threshold

        # Log the comparison
        if comparison == ComparisonResult.IMPROVED:
            logger.info(
                f"Model improved on {metric_name}: {baseline_value:.4f} -> {current_value:.4f} "
                f"(+{improvement:.4f}, +{improvement_pct:.2f}%)"
            )
        elif comparison == ComparisonResult.DEGRADED:
            logger.warning(
                f"Model degraded on {metric_name}: {baseline_value:.4f} -> {current_value:.4f} "
                f"({improvement:.4f}, {improvement_pct:.2f}%)"
            )
        else:
            logger.info(f"Model performance unchanged on {metric_name}: {current_value:.4f}")

        return result
