"""Module for loading baseline models."""

from pathlib import Path
from typing import Dict, Any, Optional
import json
import pickle
import time
import hashlib
import mlflow
from ..utils.mlflow_config import mlflow_run_context, log_step_parameters, log_step_metrics, log_model_artifact
import logging

logger = logging.getLogger(__name__)


class BaselineModelLoader:
    """Handles loading of baseline models from various sources."""

    def __init__(self, mlflow_tracking_uri: Optional[str] = None):
        self.mlflow_tracking_uri = mlflow_tracking_uri
        if mlflow_tracking_uri:
            mlflow.set_tracking_uri(mlflow_tracking_uri)

    def load_from_mlflow(self, model_name: str, version: Optional[str] = None,
                        run_id: str = "baseline_load", metaflow_run_id: str = "") -> Any:
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
                "metaflow.run_id": metaflow_run_id
            }
        ):
            try:
                # Log parameters
                log_step_parameters({
                    "model_name": model_name,
                    "model_version": version or "latest",
                    "source": "mlflow_registry"
                })

                if version:
                    model_uri = f"models:/{model_name}/{version}"
                else:
                    model_uri = f"models:/{model_name}/latest"

                model = mlflow.pyfunc.load_model(model_uri)

                # Log metrics
                load_time = time.time() - start_time
                log_step_metrics({
                    "load_time_seconds": load_time,
                    "model_loaded": 1
                })

                # Log model metadata if available
                try:
                    model_info = mlflow.models.get_model_info(model_uri)
                    mlflow.set_tag("model.run_id", model_info.run_id)
                    mlflow.set_tag("model.model_uuid", model_info.model_uuid)
                except Exception as e:
                    logger.warning(f"Could not retrieve model metadata: {e}")

                logger.info(f"Successfully loaded model {model_name} (version: {version or 'latest'})")
                return model

            except Exception as e:
                log_step_metrics({"model_loaded": 0})
                logger.error(f"Failed to load model from MLflow: {e}")
                raise

    def load_from_path(self, model_path: Path, run_id: str = "baseline_load",
                      metaflow_run_id: str = "") -> Any:
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
                "metaflow.run_id": metaflow_run_id
            }
        ):
            try:
                if not model_path.exists():
                    raise FileNotFoundError(f"Model not found at: {model_path}")

                # Calculate file hash for integrity
                with open(model_path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()

                # Log parameters
                log_step_parameters({
                    "model_path": str(model_path),
                    "model_format": model_path.suffix,
                    "source": "file_path",
                    "file_hash": file_hash,
                    "file_size_bytes": model_path.stat().st_size
                })

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
                log_step_metrics({
                    "load_time_seconds": load_time,
                    "model_loaded": 1
                })

                # Log the model file as artifact
                log_model_artifact(str(model_path), "baseline_model")

                logger.info(f"Successfully loaded model from {model_path}")
                return model

            except Exception as e:
                log_step_metrics({"model_loaded": 0})
                logger.error(f"Failed to load model from path: {e}")
                raise

    def load_mock_model(self, run_id: str = "baseline_load", metaflow_run_id: str = "") -> Dict[str, Any]:
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
                        "auroc": 0.91
                    },
                    "metadata": {
                        "training_samples": 50000,
                        "features": 100,
                        "description": "Mock baseline model for testing"
                    }
                }

                # Log parameters
                log_step_parameters({
                    "model_type": mock_model["type"],
                    "model_version": mock_model["version"],
                    "algorithm": mock_model["algorithm"],
                    "source": "mock",
                    "training_samples": mock_model["metadata"]["training_samples"],
                    "features": mock_model["metadata"]["features"]
                })

                # Log baseline metrics
                log_step_metrics({
                    "baseline_accuracy": mock_model["metrics"]["accuracy"],
                    "baseline_precision": mock_model["metrics"]["precision"],
                    "baseline_recall": mock_model["metrics"]["recall"],
                    "baseline_f1_score": mock_model["metrics"]["f1_score"],
                    "baseline_auroc": mock_model["metrics"]["auroc"],
                    "load_time_seconds": time.time() - start_time,
                    "model_loaded": 1
                })

                logger.info("Successfully loaded mock baseline model")
                return mock_model

            except Exception as e:
                log_step_metrics({"model_loaded": 0})
                logger.error(f"Failed to load mock model: {e}")
                raise

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
