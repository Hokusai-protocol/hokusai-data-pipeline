"""Model manager module for preview pipeline."""

import pickle
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MockModel:
    """Mock model for test mode."""
    model_type: str = "mock_baseline"
    version: str = "1.0.0"
    metrics: Dict[str, float] = None
    
    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {
                "accuracy": 0.85,
                "precision": 0.83,
                "recall": 0.87,
                "f1": 0.85,
                "auroc": 0.91
            }
            
    def predict(self, X):
        """Generate mock predictions."""
        n_samples = len(X) if hasattr(X, '__len__') else X.shape[0]
        # Generate slightly biased predictions for realism
        return np.random.choice([0, 1], size=n_samples, p=[0.45, 0.55])
        
    def predict_proba(self, X):
        """Generate mock probability predictions."""
        n_samples = len(X) if hasattr(X, '__len__') else X.shape[0]
        # Generate realistic-looking probabilities
        proba = np.random.rand(n_samples, 2)
        # Add some bias and normalize
        proba[:, 1] += 0.1
        proba = proba / proba.sum(axis=1, keepdims=True)
        return proba


class PreviewModelManager:
    """Manages model loading and caching for preview pipeline."""
    
    DEFAULT_MODEL_PATH = "models/baseline.pkl"
    
    def __init__(self, enable_cache: bool = True):
        """
        Initialize PreviewModelManager.
        
        Args:
            enable_cache: Whether to enable model caching
        """
        self.enable_cache = enable_cache
        self._cache = {}
        
    def load_baseline_model(self, model_path: Optional[Union[str, Path]] = None) -> Any:
        """
        Load baseline model from file.
        
        Args:
            model_path: Path to model file. If None, uses default path.
            
        Returns:
            Loaded model object
            
        Raises:
            FileNotFoundError: If model file not found
            ValueError: If model loading fails
        """
        if model_path is None:
            model_path = Path(self.DEFAULT_MODEL_PATH)
        else:
            model_path = Path(model_path)
            
        # Check cache first
        if self.enable_cache and str(model_path) in self._cache:
            logger.info(f"Loading model from cache: {model_path}")
            return self._cache[str(model_path)]
            
        if not model_path.exists():
            raise FileNotFoundError(f"Baseline model not found at: {model_path}")
            
        try:
            with open(model_path, 'rb') as f:
                model = pickle.load(f)
                
            # Cache the model
            if self.enable_cache:
                self._cache[str(model_path)] = model
                
            logger.info(f"Successfully loaded model from: {model_path}")
            return model
            
        except Exception as e:
            raise ValueError(f"Failed to load model: {str(e)}")
            
    def load_model_metadata(self, metadata_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load model metadata from JSON file.
        
        Args:
            metadata_path: Path to metadata file
            
        Returns:
            Model metadata dictionary
        """
        metadata_path = Path(metadata_path)
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
            
        return metadata
        
    def create_mock_baseline(self) -> MockModel:
        """
        Create a mock baseline model for test mode.
        
        Returns:
            Mock model with predefined performance metrics
        """
        logger.info("Creating mock baseline model for test mode")
        return MockModel()
        
    def check_compatibility(self, model: Any) -> bool:
        """
        Check if model has required methods.
        
        Args:
            model: Model to check
            
        Returns:
            True if compatible, False otherwise
        """
        required_methods = ['predict', 'predict_proba']
        
        for method in required_methods:
            if not hasattr(model, method) or not callable(getattr(model, method)):
                logger.warning(f"Model missing required method: {method}")
                return False
                
        return True
        
    def get_model_metrics(self, model: Any) -> Dict[str, float]:
        """
        Get metrics from model object.
        
        Args:
            model: Model object
            
        Returns:
            Dictionary of metrics
        """
        if hasattr(model, 'metrics'):
            return model.metrics
            
        # Return empty dict if no metrics available
        logger.warning("Model has no metrics attribute")
        return {}
        
    def clear_cache(self):
        """Clear the model cache."""
        self._cache.clear()
        logger.info("Model cache cleared")