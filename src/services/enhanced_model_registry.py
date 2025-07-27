"""Enhanced model registry with event emission capabilities."""

import logging
from typing import Any, Dict, Optional

from hokusai.core.registry import ModelRegistry, ModelRegistryEntry, RegistryException
from .model_registry_hooks import get_registry_hooks

logger = logging.getLogger(__name__)


class EnhancedModelRegistry(ModelRegistry):
    """Extended model registry that emits events on successful registration."""
    
    def __init__(self, *args, **kwargs):
        """Initialize enhanced registry with hooks."""
        super().__init__(*args, **kwargs)
        self.hooks = get_registry_hooks()
    
    def register_tokenized_model_with_events(
        self,
        model_uri: str,
        model_name: str,
        token_id: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        additional_tags: Optional[Dict[str, str]] = None,
        contributor_address: Optional[str] = None,
        experiment_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a tokenized model and emit ready_to_deploy event if it meets baseline.
        
        This extends the base register_tokenized_model method to:
        1. Validate the model meets baseline requirements
        2. Register the model in MLflow
        3. Emit a model_ready_to_deploy message if successful
        
        Args:
            model_uri: MLflow model URI (e.g., "runs:/abc123/model")
            model_name: Name for the registered model
            token_id: Hokusai token ID (e.g., "msg-ai")
            metric_name: Performance metric name (e.g., "reply_rate")
            baseline_value: Baseline performance value
            current_value: Current model's performance value
            additional_tags: Optional additional tags
            contributor_address: Optional contributor Ethereum address
            experiment_name: Optional experiment name
            
        Returns:
            Dict with registration details
            
        Raises:
            ValueError: Invalid parameters or model doesn't meet baseline
            RegistryException: Registration failed
        """
        # Validate current value meets baseline
        if current_value < baseline_value:
            raise ValueError(
                f"Model does not meet baseline requirement: "
                f"{current_value} < {baseline_value}"
            )
        
        # Get MLflow run ID from model URI
        mlflow_run_id = self._extract_run_id_from_uri(model_uri)
        
        # Register the model using parent method
        # Note: parent method doesn't have current_value parameter
        result = self.register_tokenized_model(
            model_uri=model_uri,
            model_name=model_name,
            token_id=token_id,
            metric_name=metric_name,
            baseline_value=baseline_value,
            additional_tags=additional_tags
        )
        
        # Add current_value to result
        result["current_value"] = current_value
        
        # Extract model version for use in event
        model_version = str(result.get("version", "1"))
        
        # Generate a unique model ID
        model_id = f"{model_name}/{model_version}/{token_id}"
        
        # Emit model_ready_to_deploy event
        try:
            event_success = self.hooks.on_model_registered_with_baseline(
                model_id=model_id,
                model_name=model_name,
                model_version=model_version,
                mlflow_run_id=mlflow_run_id,
                token_id=token_id,
                metric_name=metric_name,
                baseline_value=baseline_value,
                current_value=current_value,
                tags=additional_tags,
                contributor_address=contributor_address,
                experiment_name=experiment_name
            )
            
            if event_success:
                logger.info(
                    f"Successfully emitted model_ready_to_deploy event for {model_id}"
                )
                result["event_emitted"] = True
            else:
                logger.warning(
                    f"Failed to emit model_ready_to_deploy event for {model_id}"
                )
                result["event_emitted"] = False
                
        except Exception as e:
            logger.error(f"Error emitting event: {str(e)}")
            result["event_emitted"] = False
            result["event_error"] = str(e)
        
        return result
    
    def register_baseline_with_events(
        self,
        model: Any,
        model_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        token_id: Optional[str] = None,
        metric_name: Optional[str] = None,
        baseline_value: Optional[float] = None,
        **kwargs
    ) -> ModelRegistryEntry:
        """Register a baseline model with optional event emission.
        
        If token_id, metric_name, and baseline_value are provided,
        this will emit a model_ready_to_deploy event.
        
        Args:
            model: HokusaiModel instance
            model_type: Type of model
            metadata: Additional metadata
            token_id: Optional Hokusai token ID for event emission
            metric_name: Optional metric name for event emission
            baseline_value: Optional baseline value for event emission
            **kwargs: Additional parameters
            
        Returns:
            ModelRegistryEntry
        """
        # Register using parent method
        entry = self.register_baseline(
            model=model,
            model_type=model_type,
            metadata=metadata,
            **kwargs
        )
        
        # If token information is provided, emit event
        if all([token_id, metric_name, baseline_value is not None]):
            try:
                # For baseline models, current_value equals baseline_value
                event_success = self.hooks.on_model_registered_with_baseline(
                    model_id=entry.model_id,
                    model_name=model_type,
                    model_version=entry.version,
                    mlflow_run_id=entry.mlflow_version or "unknown",
                    token_id=token_id,
                    metric_name=metric_name,
                    baseline_value=baseline_value,
                    current_value=baseline_value,  # Baseline meets its own baseline
                    tags=metadata
                )
                
                if event_success:
                    logger.info(
                        f"Emitted baseline model_ready_to_deploy event for {entry.model_id}"
                    )
            except Exception as e:
                logger.error(f"Failed to emit baseline event: {str(e)}")
        
        return entry
    
    def _extract_run_id_from_uri(self, model_uri: str) -> str:
        """Extract MLflow run ID from model URI.
        
        Args:
            model_uri: Model URI (e.g., "runs:/abc123/model")
            
        Returns:
            Run ID
        """
        if model_uri.startswith("runs:/"):
            parts = model_uri.split("/")
            if len(parts) >= 2:
                return parts[1]
        
        # If we can't extract it, return the full URI
        return model_uri