"""Module for loading baseline models."""

from pathlib import Path
from typing import Dict, Any, Optional
import json
import pickle
import mlflow


class BaselineModelLoader:
    """Handles loading of baseline models from various sources."""
    
    def __init__(self, mlflow_tracking_uri: Optional[str] = None):
        self.mlflow_tracking_uri = mlflow_tracking_uri
        if mlflow_tracking_uri:
            mlflow.set_tracking_uri(mlflow_tracking_uri)
    
    def load_from_mlflow(self, model_name: str, version: Optional[str] = None) -> Any:
        """Load model from MLflow registry.
        
        Args:
            model_name: Name of the model in registry
            version: Model version (defaults to latest)
            
        Returns:
            Loaded model object
        """
        if version:
            model_uri = f"models:/{model_name}/{version}"
        else:
            model_uri = f"models:/{model_name}/latest"
        
        model = mlflow.pyfunc.load_model(model_uri)
        return model
    
    def load_from_path(self, model_path: Path) -> Any:
        """Load model from file path.
        
        Args:
            model_path: Path to model file
            
        Returns:
            Loaded model object
        """
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at: {model_path}")
        
        # Determine file type and load accordingly
        if model_path.suffix == ".pkl":
            with open(model_path, "rb") as f:
                return pickle.load(f)
        elif model_path.suffix == ".json":
            with open(model_path, "r") as f:
                return json.load(f)
        else:
            raise ValueError(f"Unsupported model format: {model_path.suffix}")
    
    def load_mock_model(self) -> Dict[str, Any]:
        """Load a mock model for testing.
        
        Returns:
            Mock model dictionary
        """
        return {
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