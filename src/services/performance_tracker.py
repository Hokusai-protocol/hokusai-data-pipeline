"""Performance tracking service for model improvements and attestation generation."""

import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, List
import mlflow

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Track and verify performance improvements with attestation generation.
    
    This service provides:
    - Performance delta calculation
    - Attestation generation for improvements
    - Contributor impact tracking
    - DeltaOne value computation
    """

    def __init__(self):
        """Initialize the performance tracker."""
        logger.info("Initialized PerformanceTracker")

    def track_improvement(self, baseline_metrics: Dict[str, float],
                         improved_metrics: Dict[str, float],
                         data_contribution: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """Track and verify performance improvements.
        
        Args:
            baseline_metrics: Metrics from the baseline model
            improved_metrics: Metrics from the improved model
            data_contribution: Information about the data contribution
            
        Returns:
            Tuple of (delta metrics, attestation)

        """
        # Validate inputs
        self._validate_metrics(baseline_metrics)
        self._validate_metrics(improved_metrics)

        # Calculate performance delta
        delta = self._calculate_delta(baseline_metrics, improved_metrics)

        # Generate attestation
        attestation = self._generate_attestation(delta, data_contribution)

        # Log to MLFlow
        self._log_improvement_to_mlflow(delta, attestation, data_contribution)

        logger.info(f"Tracked improvement with delta: {delta}")

        return delta, attestation

    def _calculate_delta(self, baseline_metrics: Dict[str, float],
                        improved_metrics: Dict[str, float],
                        percentage: bool = False) -> Dict[str, float]:
        """Calculate the delta between baseline and improved metrics.
        
        Args:
            baseline_metrics: Baseline model metrics
            improved_metrics: Improved model metrics
            percentage: Whether to include percentage improvements
            
        Returns:
            Dictionary of metric improvements

        """
        delta = {}

        for metric_name, baseline_value in baseline_metrics.items():
            if metric_name not in improved_metrics:
                raise ValueError(f"Metric '{metric_name}' missing in improved metrics")

            improved_value = improved_metrics[metric_name]
            improvement = improved_value - baseline_value

            delta[metric_name] = round(improvement, 6)

            if percentage and baseline_value != 0:
                pct_improvement = (improvement / baseline_value) * 100
                delta[f"{metric_name}_pct"] = round(pct_improvement, 2)

        return delta

    def _generate_attestation(self, delta: Dict[str, float],
                            data_contribution: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an attestation for the performance improvement.
        
        Args:
            delta: Performance improvements
            data_contribution: Data contribution metadata
            
        Returns:
            Attestation dictionary with hash and signature placeholder

        """
        attestation = {
            "version": "1.0",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "delta_metrics": delta,
            "contributor_info": {
                "id": data_contribution.get("contributor_id", "unknown"),
                "address": data_contribution.get("contributor_address", ""),
            },
            "data_contribution": {
                "dataset_hash": data_contribution.get("dataset_hash", ""),
                "data_size": data_contribution.get("data_size", 0),
                "quality_score": data_contribution.get("data_quality_score", 0)
            },
            "deltaone_value": self._generate_deltaone_value(delta)
        }

        # Generate attestation hash
        attestation_string = json.dumps(attestation, sort_keys=True)
        attestation_hash = hashlib.sha256(attestation_string.encode()).hexdigest()

        attestation["attestation_hash"] = f"0x{attestation_hash}"
        attestation["signature"] = "placeholder_for_oracle_signature"  # To be implemented

        return attestation

    def log_contribution_impact(self, contributor_address: str,
                              model_id: str,
                              delta: Dict[str, float]) -> None:
        """Log contributor's impact on model performance.
        
        Args:
            contributor_address: Ethereum address of contributor
            model_id: ID of the improved model
            delta: Performance improvements

        """
        try:
            impact_score = self._calculate_impact_score(delta)

            # Log to MLFlow
            mlflow.log_params({
                "contributor_address": contributor_address,
                "model_id": model_id,
                "impact_score": impact_score,
                "contribution_timestamp": datetime.utcnow().isoformat()
            })

            mlflow.log_metrics({
                "contributor_impact_score": impact_score,
                "total_improvement": sum(abs(v) for v in delta.values() if isinstance(v, (int, float)))
            })

            logger.info(f"Logged contribution impact for {contributor_address}: {impact_score}")

        except Exception as e:
            logger.error(f"Failed to log contribution impact: {str(e)}")
            raise

    def _calculate_impact_score(self, delta: Dict[str, float]) -> float:
        """Calculate a unified impact score from delta metrics.
        
        Args:
            delta: Performance improvements
            
        Returns:
            Impact score (0-1 scale)

        """
        # Simple average of absolute improvements
        improvements = [abs(v) for v in delta.values() if isinstance(v, (int, float))]

        if not improvements:
            return 0.0

        return sum(improvements) / len(improvements)

    def _generate_deltaone_value(self, delta: Dict[str, float]) -> float:
        """Generate DeltaOne value based on improvements.
        
        Args:
            delta: Performance improvements
            
        Returns:
            DeltaOne value for reward calculation

        """
        # DeltaOne formula: weighted sum of improvements * 100
        # This is a simplified version - actual formula would be more complex

        weights = {
            "accuracy": 1.0,
            "auroc": 0.8,
            "f1_score": 0.9,
            "precision": 0.7,
            "recall": 0.7
        }

        deltaone = 0.0
        for metric, improvement in delta.items():
            if metric in weights and not metric.endswith("_pct"):
                deltaone += improvement * weights[metric] * 100

        return round(max(0, deltaone), 2)

    def _validate_metrics(self, metrics: Any) -> bool:
        """Validate metrics format and values.
        
        Args:
            metrics: Metrics to validate
            
        Returns:
            True if valid
            
        Raises:
            ValueError: If metrics are invalid

        """
        if not isinstance(metrics, dict):
            raise ValueError("Metrics must be a dictionary")

        if not metrics:
            raise ValueError("Metrics cannot be empty")

        for key, value in metrics.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"Metric '{key}' must be numeric, got {type(value)}")

        return True

    def _log_improvement_to_mlflow(self, delta: Dict[str, float],
                                 attestation: Dict[str, Any],
                                 data_contribution: Dict[str, Any]) -> None:
        """Log improvement details to MLFlow.
        
        Args:
            delta: Performance improvements
            attestation: Generated attestation
            data_contribution: Data contribution metadata

        """
        try:
            # Log delta metrics with _improvement suffix
            improvement_metrics = {
                f"{k}_improvement": v for k, v in delta.items()
                if not k.endswith("_pct")
            }
            mlflow.log_metrics(improvement_metrics)

            # Log attestation as artifact
            mlflow.log_dict(attestation, artifact_file="attestation.json")

            # Log contribution metadata
            mlflow.log_params({
                "contributor_id": data_contribution.get("contributor_id", "unknown"),
                "dataset_hash": data_contribution.get("dataset_hash", ""),
                "deltaone_value": attestation["deltaone_value"]
            })

        except Exception as e:
            logger.error(f"Failed to log to MLFlow: {str(e)}")
            # Don't raise - logging failure shouldn't break the pipeline

    def _aggregate_impacts(self, impacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate multiple contribution impacts by model.
        
        Args:
            impacts: List of individual contribution impacts
            
        Returns:
            Aggregated impacts by model

        """
        aggregated = {}

        for impact in impacts:
            model = impact["model"]
            delta = impact["delta"]

            if model not in aggregated:
                aggregated[model] = {
                    "total_improvement": 0,
                    "contribution_count": 0,
                    "metrics": {}
                }

            # Sum improvements
            for metric, value in delta.items():
                if metric not in aggregated[model]["metrics"]:
                    aggregated[model]["metrics"][metric] = 0
                aggregated[model]["metrics"][metric] += value

            aggregated[model]["total_improvement"] = sum(
                abs(v) for v in aggregated[model]["metrics"].values()
            )
            aggregated[model]["contribution_count"] += 1

        return aggregated

    def get_contributor_impact(self, contributor_address: str) -> Dict[str, Any]:
        """Get aggregated impact data for a contributor.
        
        Args:
            contributor_address: Ethereum address of the contributor
            
        Returns:
            Dictionary with contributor's total impact across all models

        """
        # In a real implementation, this would query MLFlow or a database
        # For now, returning mock data structure
        logger.info(f"Getting impact data for contributor: {contributor_address}")

        return {
            "total_models_improved": 0,
            "total_improvement_score": 0.0,
            "contributions": [],
            "first_contribution": None,
            "last_contribution": None
        }
