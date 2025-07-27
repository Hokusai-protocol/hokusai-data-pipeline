"""Hooks for model registry events."""

import logging
from typing import Any, Dict, Optional

from ..events.publishers.factory import get_publisher
from ..events.publishers.base import PublisherException
from ..validation.metrics import MetricValidator

logger = logging.getLogger(__name__)


class ModelRegistryHooks:
    """Handles post-registration events and validations."""
    
    def __init__(self):
        """Initialize hooks with publisher and validator."""
        self.publisher = get_publisher()
        self.validator = MetricValidator()
    
    def on_model_registered_with_baseline(
        self,
        model_id: str,
        model_name: str,
        model_version: str,
        mlflow_run_id: str,
        token_id: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        tags: Optional[Dict[str, str]] = None,
        contributor_address: Optional[str] = None,
        experiment_name: Optional[str] = None
    ) -> bool:
        """Hook called after a model is registered and passes baseline validation.
        
        This emits a model_ready_to_deploy message to the configured queue.
        
        Args:
            model_id: Unique model identifier
            model_name: Registered model name
            model_version: Model version
            mlflow_run_id: MLflow run ID
            token_id: Hokusai token ID
            metric_name: Performance metric name
            baseline_value: Baseline performance value
            current_value: Current model's performance value
            tags: Optional model tags
            contributor_address: Optional contributor Ethereum address
            experiment_name: Optional experiment name
            
        Returns:
            True if message was successfully emitted
        """
        try:
            # Validate baseline and current values
            if not self.validator.validate_baseline(metric_name, baseline_value):
                logger.error(f"Invalid baseline value for {metric_name}: {baseline_value}")
                return False
            
            if not self.validator.validate_metric_value(metric_name, current_value):
                logger.error(f"Invalid metric value for {metric_name}: {current_value}")
                return False
            
            # Check if model meets baseline
            if current_value < baseline_value:
                logger.warning(
                    f"Model {model_id} does not meet baseline: "
                    f"{current_value} < {baseline_value}"
                )
                return False
            
            # Emit model_ready_to_deploy message
            success = self.publisher.publish_model_ready(
                model_id=model_id,
                token_symbol=token_id,  # token_id is used as token_symbol
                metric_name=metric_name,
                baseline_value=baseline_value,
                current_value=current_value,
                model_name=model_name,
                model_version=model_version,
                mlflow_run_id=mlflow_run_id,
                contributor_address=contributor_address,
                experiment_name=experiment_name,
                tags=tags
            )
            
            if success:
                logger.info(
                    f"Emitted model_ready_to_deploy for {model_id} "
                    f"(token: {token_id}, improvement: "
                    f"{((current_value - baseline_value) / baseline_value * 100):.2f}%)"
                )
            else:
                logger.error(f"Failed to emit model_ready_to_deploy for {model_id}")
            
            return success
            
        except PublisherException as e:
            logger.error(f"Publisher error: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in model registration hook: {str(e)}")
            return False
    
    def on_model_validation_failed(
        self,
        model_id: str,
        reason: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        baseline_value: Optional[float] = None
    ) -> None:
        """Hook called when model validation fails.
        
        This can be used for monitoring and alerting.
        
        Args:
            model_id: Model that failed validation
            reason: Reason for validation failure
            metric_name: Metric that failed
            metric_value: Actual metric value
            baseline_value: Expected baseline value
        """
        logger.warning(
            f"Model {model_id} failed validation: {reason}. "
            f"Metric: {metric_name}, Value: {metric_value}, "
            f"Baseline: {baseline_value}"
        )
        
        # Could emit a different event type here for monitoring
        # For now, just log the failure


# Singleton instance
_hooks_instance: Optional[ModelRegistryHooks] = None


def get_registry_hooks() -> ModelRegistryHooks:
    """Get singleton hooks instance.
    
    Returns:
        ModelRegistryHooks instance
    """
    global _hooks_instance
    
    if _hooks_instance is None:
        _hooks_instance = ModelRegistryHooks()
    
    return _hooks_instance