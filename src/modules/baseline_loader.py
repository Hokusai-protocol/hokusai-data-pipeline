"""Module for loading baseline models."""

import hashlib
import json
import logging
import pickle
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import mlflow
from mlflow.tracking import MlflowClient

from ..utils.mlflow_config import (
    log_model_artifact,
    log_step_metrics,
    log_step_parameters,
    mlflow_run_context,
)

logger = logging.getLogger(__name__)


class BaselineModelLoader:
    """Handles loading of baseline models from various sources."""

    def __init__(self, mlflow_tracking_uri: Optional[str] = None) -> None:
        self.mlflow_tracking_uri = mlflow_tracking_uri
        if mlflow_tracking_uri:
            mlflow.set_tracking_uri(mlflow_tracking_uri)
        self.client = MlflowClient()
        self.cache = {}

    def load_from_mlflow(
        self,
        model_name: str,
        version: Optional[str] = None,
        run_id: str = "baseline_load",
        metaflow_run_id: str = "",
    ) -> Any:
        """Load model from MLflow registry with tracking.

        Args:
            model_name: Name of the model in registry
            version: Model version (defaults to latest)
            run_id: Unique run identifier
            metaflow_run_id: Metaflow run identifier

        Returns:
            Loaded model object

        """
        start_time = time.time()
        run_name = f"baseline_load_mlflow_{run_id}"

        with mlflow_run_context(
            run_name=run_name,
            tags={
                "pipeline.step": "load_baseline_model",
                "pipeline.run_id": run_id,
                "metaflow.run_id": metaflow_run_id,
            },
        ):
            try:
                # Log parameters
                log_step_parameters(
                    {
                        "model_name": model_name,
                        "model_version": version or "latest",
                        "source": "mlflow_registry",
                    }
                )

                if version:
                    model_uri = f"models:/{model_name}/{version}"
                else:
                    model_uri = f"models:/{model_name}/latest"

                model = mlflow.pyfunc.load_model(model_uri)

                # Log metrics
                load_time = time.time() - start_time
                log_step_metrics({"load_time_seconds": load_time, "model_loaded": 1})

                # Log model metadata if available
                try:
                    model_info = mlflow.models.get_model_info(model_uri)
                    mlflow.set_tag("model.run_id", model_info.run_id)
                    mlflow.set_tag("model.model_uuid", model_info.model_uuid)
                except Exception as e:
                    logger.warning(f"Could not retrieve model metadata: {e}")

                logger.info(
                    f"Successfully loaded model {model_name} (version: {version or 'latest'})"
                )
                return model

            except Exception as e:
                log_step_metrics({"model_loaded": 0})
                logger.error(f"Failed to load model from MLflow: {e}")
                raise

    def load_from_path(
        self, model_path: Path, run_id: str = "baseline_load", metaflow_run_id: str = ""
    ) -> Any:
        """Load model from file path with tracking.

        Args:
            model_path: Path to model file
            run_id: Unique run identifier
            metaflow_run_id: Metaflow run identifier

        Returns:
            Loaded model object

        """
        start_time = time.time()
        run_name = f"baseline_load_path_{run_id}"

        with mlflow_run_context(
            run_name=run_name,
            tags={
                "pipeline.step": "load_baseline_model",
                "pipeline.run_id": run_id,
                "metaflow.run_id": metaflow_run_id,
            },
        ):
            try:
                if not model_path.exists():
                    raise FileNotFoundError(f"Model not found at: {model_path}")

                # Calculate file hash for integrity
                with open(model_path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()

                # Log parameters
                log_step_parameters(
                    {
                        "model_path": str(model_path),
                        "model_format": model_path.suffix,
                        "source": "file_path",
                        "file_hash": file_hash,
                        "file_size_bytes": model_path.stat().st_size,
                    }
                )

                # Determine file type and load accordingly
                if model_path.suffix == ".pkl":
                    with open(model_path, "rb") as f:
                        model = pickle.load(f)
                elif model_path.suffix == ".json":
                    with open(model_path) as f:
                        model = json.load(f)
                else:
                    raise ValueError(f"Unsupported model format: {model_path.suffix}")

                # Log metrics
                load_time = time.time() - start_time
                log_step_metrics({"load_time_seconds": load_time, "model_loaded": 1})

                # Log the model file as artifact
                log_model_artifact(str(model_path), "baseline_model")

                logger.info(f"Successfully loaded model from {model_path}")
                return model

            except Exception as e:
                log_step_metrics({"model_loaded": 0})
                logger.error(f"Failed to load model from path: {e}")
                raise

    def load_mock_model(
        self, run_id: str = "baseline_load", metaflow_run_id: str = ""
    ) -> dict[str, Any]:
        """Load a mock model for testing with tracking.

        Args:
            run_id: Unique run identifier
            metaflow_run_id: Metaflow run identifier

        Returns:
            Mock model dictionary

        """
        start_time = time.time()
        run_name = f"baseline_load_mock_{run_id}"

        with mlflow_run_context(run_name, "load_baseline_model", run_id, metaflow_run_id):
            try:
                mock_model = {
                    "type": "mock_baseline_model",
                    "version": "1.0.0",
                    "algorithm": "mock_algorithm",
                    "training_date": "2024-01-01",
                    "metrics": {
                        "accuracy": 0.85,
                        "precision": 0.83,
                        "recall": 0.87,
                        "f1_score": 0.85,
                        "auroc": 0.91,
                    },
                    "metadata": {
                        "training_samples": 50000,
                        "features": 100,
                        "description": "Mock baseline model for testing",
                    },
                }

                # Log parameters
                log_step_parameters(
                    {
                        "model_type": mock_model["type"],
                        "model_version": mock_model["version"],
                        "algorithm": mock_model["algorithm"],
                        "source": "mock",
                        "training_samples": mock_model["metadata"]["training_samples"],
                        "features": mock_model["metadata"]["features"],
                    }
                )

                # Log baseline metrics
                log_step_metrics(
                    {
                        "baseline_accuracy": mock_model["metrics"]["accuracy"],
                        "baseline_precision": mock_model["metrics"]["precision"],
                        "baseline_recall": mock_model["metrics"]["recall"],
                        "baseline_f1_score": mock_model["metrics"]["f1_score"],
                        "baseline_auroc": mock_model["metrics"]["auroc"],
                        "load_time_seconds": time.time() - start_time,
                        "model_loaded": 1,
                    }
                )

                logger.info("Successfully loaded mock baseline model")
                return mock_model

            except Exception as e:
                log_step_metrics({"model_loaded": 0})
                logger.error(f"Failed to load mock model: {e}")
                raise

    def load_baseline_model(self, model_name: str, use_cache: bool = True):
        """Load baseline model with caching support.
        
        Args:
            model_name: Name of the model
            use_cache: Whether to use cached model if available
            
        Returns:
            Tuple of (model, version_info)
        """
        # Check cache first
        if use_cache and model_name in self.cache:
            logger.info(f"Loading model {model_name} from cache")
            return self.cache[model_name]
            
        # Get latest production version
        version = self._get_latest_production_version(model_name)
        if version:
            model_uri = f"models:/{model_name}/{version.version}"
            model = mlflow.pyfunc.load_model(model_uri)
            
            version_info = {
                "version": version.version,
                "stage": version.current_stage,
                "run_id": version.run_id
            }
            
            # Cache the result
            if use_cache:
                self.cache[model_name] = (model, version_info)
                
            return model, version_info
        
        # Try previous version as fallback
        prev_version = self._get_previous_version(model_name)
        if prev_version:
            model_uri = f"models:/{model_name}/{prev_version.version}"
            model = mlflow.pyfunc.load_model(model_uri)
            
            version_info = {
                "version": prev_version.version,
                "stage": prev_version.current_stage,
                "run_id": prev_version.run_id
            }
            
            # Cache the result
            if use_cache:
                self.cache[model_name] = (model, version_info)
                
            return model, version_info
            
        raise ValueError(f"No baseline model found for {model_name}")
    
    def _get_latest_production_version(self, model_name: str):
        """Get the latest production version of a model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            Model version object or None
        """
        versions = self.client.search_model_versions(f"name='{model_name}'")
        
        # Filter production versions
        prod_versions = [v for v in versions if v.current_stage == "Production"]
        
        if not prod_versions:
            return None
            
        # Sort by creation timestamp (latest first)
        prod_versions.sort(key=lambda v: v.creation_timestamp, reverse=True)
        
        return prod_versions[0]
    
    def _get_previous_version(self, model_name: str, current_version: str = None):
        """Get the previous version of a model.
        
        Args:
            model_name: Name of the model
            current_version: Current version to find the previous of (optional)
            
        Returns:
            Model version object or None
        """
        versions = self.client.search_model_versions(f"name='{model_name}'")
        
        if not versions:
            return None
            
        # Sort by version number (descending)
        versions.sort(key=lambda v: int(v.version), reverse=True)
        
        if current_version:
            # Find the version before the specified current version
            for i, v in enumerate(versions):
                if v.version == current_version:
                    # Return the next version in the list (which is previous due to reverse sort)
                    return versions[i + 1] if i + 1 < len(versions) else None
            return None
        else:
            # Return second latest if exists, else None (not the latest)
            return versions[1] if len(versions) > 1 else None
    
    def load_specific_version(self, model_name: str, version: str):
        """Load a specific version of a model.
        
        Args:
            model_name: Name of the model
            version: Version to load
            
        Returns:
            Loaded model
        """
        model_uri = f"models:/{model_name}/{version}"
        return mlflow.pyfunc.load_model(model_uri)
    
    def get_model_metadata(self, model_name: str, version: str = None):
        """Get metadata for a model.
        
        Args:
            model_name: Name of the model
            version: Specific version to get metadata for (optional)
            
        Returns:
            Dictionary with model metadata
        """
        try:
            if version:
                # Get metadata for specific version
                model_version = self.client.get_model_version(model_name, version)
                return {
                    "name": model_name,
                    "version": model_version.version,
                    "stage": model_version.current_stage,
                    "run_id": model_version.run_id,
                    "tags": model_version.tags,
                    "created_at": datetime.fromtimestamp(model_version.creation_timestamp / 1000),
                    "description": model_version.description
                }
            else:
                # Get general model metadata
                model = self.client.get_registered_model(model_name)
                versions = self.client.search_model_versions(f"name='{model_name}'")
                
                return {
                    "name": model.name,
                    "description": model.description,
                    "tags": model.tags,
                    "latest_versions": [
                        {
                            "version": v.version,
                            "stage": v.current_stage,
                            "description": v.description
                        }
                        for v in versions[:5]  # Last 5 versions
                    ]
                }
        except Exception as e:
            logger.error(f"Error getting metadata for {model_name}: {e}")
            return None
    
    def list_available_baselines(self, model_name: str = None):
        """List available baseline models or versions.
        
        Args:
            model_name: If provided, list versions for this model
        
        Returns:
            List of model names or version information
        """
        try:
            if model_name:
                # List versions for specific model
                versions = self.client.search_model_versions(f"name='{model_name}'")
                
                # Sort by stage priority (Production first) and then by version
                stage_priority = {"Production": 0, "Staging": 1, "Archived": 2, "None": 3}
                versions.sort(key=lambda v: (stage_priority.get(v.current_stage, 3), -int(v.version)))
                
                return [
                    {
                        "version": v.version,
                        "stage": v.current_stage,
                        "tags": v.tags if hasattr(v, 'tags') else {},
                        "description": v.description if hasattr(v, 'description') else ""
                    }
                    for v in versions
                ]
            else:
                # List all model names
                models = self.client.list_registered_models()
                return [model.name for model in models]
        except Exception as e:
            logger.error(f"Error listing baseline models: {e}")
            return []
    
    def clear_cache(self):
        """Clear the model cache."""
        self.cache.clear()
        logger.info("Model cache cleared")

    def validate_model(self, model: Any) -> bool:
        """Validate that model has required attributes.

        Args:
            model: Model object to validate

        Returns:
            True if valid, raises exception otherwise

        """
        # For mock models
        if isinstance(model, dict) and model.get("type", "").startswith("mock"):
            required_keys = ["type", "version", "metrics"]
            for key in required_keys:
                if key not in model:
                    raise ValueError(f"Mock model missing required key: {key}")
            return True

        # For real models - check for predict method
        if not hasattr(model, "predict"):
            raise ValueError("Model must have a predict method")

        return True
