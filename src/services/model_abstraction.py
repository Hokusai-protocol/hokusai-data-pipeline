"""Model abstraction layer for supporting multiple models and A/B testing."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd
from datetime import datetime
import hashlib
import logging
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Supported model types in the Hokusai platform."""

    LEAD_SCORING = "lead_scoring"
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    RANKING = "ranking"
    DSPY = "dspy"


class ModelStatus(Enum):
    """Model lifecycle status."""

    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass
class ModelMetadata:
    """Metadata for model tracking and management."""

    model_id: str
    model_family: str
    version: str
    model_type: ModelType
    status: ModelStatus
    created_at: datetime
    updated_at: datetime
    training_metadata: Dict[str, Any]
    performance_metrics: Dict[str, float]
    feature_names: List[str]
    feature_types: Dict[str, str]
    contributor_address: Optional[str] = None
    baseline_model_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        data = asdict(self)
        data["model_type"] = self.model_type.value
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


class HokusaiModel(ABC):
    """Abstract base class for all Hokusai models.
    
    This class defines the interface that all models must implement
    to be compatible with the Hokusai platform's model management,
    A/B testing, and inference pipeline.
    """

    def __init__(self, model_metadata: ModelMetadata):
        """Initialize the model with metadata.
        
        Args:
            model_metadata: Model metadata including version, features, etc.

        """
        self.metadata = model_metadata
        self._model = None
        self._is_loaded = False

    @abstractmethod
    def load(self, model_path: str) -> None:
        """Load the model from disk or remote storage.
        
        Args:
            model_path: Path to the model artifact

        """
        pass

    @abstractmethod
    def predict(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Make predictions on input data.
        
        Args:
            X: Input features as numpy array or pandas DataFrame
            
        Returns:
            Predictions as numpy array

        """
        pass

    @abstractmethod
    def predict_proba(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Return prediction probabilities for classification models.
        
        Args:
            X: Input features
            
        Returns:
            Prediction probabilities

        """
        pass

    def get_model_info(self) -> Dict[str, Any]:
        """Return model metadata and configuration.
        
        Returns:
            Dictionary containing model information

        """
        return self.metadata.to_dict()

    def get_required_features(self) -> List[str]:
        """Return list of required feature names.
        
        Returns:
            List of feature names expected by the model

        """
        return self.metadata.feature_names

    def validate_input(self, X: Union[np.ndarray, pd.DataFrame]) -> bool:
        """Validate input data format and shape.
        
        Args:
            X: Input data to validate
            
        Returns:
            True if input is valid, raises ValueError otherwise

        """
        if isinstance(X, pd.DataFrame):
            # Check if all required features are present
            missing_features = set(self.metadata.feature_names) - set(X.columns)
            if missing_features:
                raise ValueError(f"Missing required features: {missing_features}")

            # Reorder columns to match expected order
            X = X[self.metadata.feature_names]

        elif isinstance(X, np.ndarray):
            # Check shape
            if X.shape[1] != len(self.metadata.feature_names):
                raise ValueError(
                    f"Expected {len(self.metadata.feature_names)} features, "
                    f"got {X.shape[1]}"
                )
        else:
            raise ValueError(f"Unsupported input type: {type(X)}")

        return True

    def preprocess(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Preprocess input data before prediction.
        
        Args:
            X: Raw input data
            
        Returns:
            Preprocessed data ready for prediction

        """
        # Default implementation - can be overridden by subclasses
        if isinstance(X, pd.DataFrame):
            return X[self.metadata.feature_names].values
        return X

    def postprocess(self, predictions: np.ndarray) -> np.ndarray:
        """Postprocess model predictions.
        
        Args:
            predictions: Raw model predictions
            
        Returns:
            Processed predictions

        """
        # Default implementation - can be overridden by subclasses
        return predictions

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded and ready for inference."""
        return self._is_loaded

    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """Return feature importance scores if available.
        
        Returns:
            Dictionary mapping feature names to importance scores

        """
        return None

    def explain_prediction(self, X: Union[np.ndarray, pd.DataFrame],
                         idx: int = 0) -> Optional[Dict[str, Any]]:
        """Explain a single prediction if supported.
        
        Args:
            X: Input data
            idx: Index of the instance to explain
            
        Returns:
            Explanation dictionary or None if not supported

        """
        return None


class ModelAdapter:
    """Adapter to convert existing models to HokusaiModel interface."""

    @staticmethod
    def create_sklearn_adapter(sklearn_model: Any,
                             metadata: ModelMetadata) -> "SklearnHokusaiModel":
        """Create a HokusaiModel adapter for scikit-learn models.
        
        Args:
            sklearn_model: Scikit-learn model instance
            metadata: Model metadata
            
        Returns:
            SklearnHokusaiModel instance

        """
        return SklearnHokusaiModel(sklearn_model, metadata)

    @staticmethod
    def create_xgboost_adapter(xgb_model: Any,
                             metadata: ModelMetadata) -> "XGBoostHokusaiModel":
        """Create a HokusaiModel adapter for XGBoost models.
        
        Args:
            xgb_model: XGBoost model instance
            metadata: Model metadata
            
        Returns:
            XGBoostHokusaiModel instance

        """
        return XGBoostHokusaiModel(xgb_model, metadata)

    @staticmethod
    def create_tensorflow_adapter(tf_model: Any,
                                metadata: ModelMetadata) -> "TensorFlowHokusaiModel":
        """Create a HokusaiModel adapter for TensorFlow models.
        
        Args:
            tf_model: TensorFlow model instance
            metadata: Model metadata
            
        Returns:
            TensorFlowHokusaiModel instance

        """
        return TensorFlowHokusaiModel(tf_model, metadata)


class SklearnHokusaiModel(HokusaiModel):
    """Adapter for scikit-learn models."""

    def __init__(self, sklearn_model: Any, metadata: ModelMetadata):
        super().__init__(metadata)
        self._model = sklearn_model
        self._is_loaded = sklearn_model is not None

    def load(self, model_path: str) -> None:
        """Load scikit-learn model from pickle file."""
        import pickle
        with open(model_path, "rb") as f:
            self._model = pickle.load(f)
        self._is_loaded = True
        logger.info(f"Loaded sklearn model from {model_path}")

    def predict(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Make predictions using sklearn model."""
        if not self._is_loaded:
            raise RuntimeError("Model not loaded")

        self.validate_input(X)
        X_processed = self.preprocess(X)
        predictions = self._model.predict(X_processed)
        return self.postprocess(predictions)

    def predict_proba(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Return prediction probabilities."""
        if not self._is_loaded:
            raise RuntimeError("Model not loaded")

        if not hasattr(self._model, "predict_proba"):
            raise NotImplementedError("Model does not support probability predictions")

        self.validate_input(X)
        X_processed = self.preprocess(X)
        return self._model.predict_proba(X_processed)

    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """Get feature importance from tree-based models."""
        if hasattr(self._model, "feature_importances_"):
            return dict(zip(
                self.metadata.feature_names,
                self._model.feature_importances_
            ))
        return None


class XGBoostHokusaiModel(HokusaiModel):
    """Adapter for XGBoost models."""

    def __init__(self, xgb_model: Any, metadata: ModelMetadata):
        super().__init__(metadata)
        self._model = xgb_model
        self._is_loaded = xgb_model is not None

    def load(self, model_path: str) -> None:
        """Load XGBoost model from file."""
        import xgboost as xgb
        self._model = xgb.Booster()
        self._model.load_model(model_path)
        self._is_loaded = True
        logger.info(f"Loaded XGBoost model from {model_path}")

    def predict(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Make predictions using XGBoost model."""
        import xgboost as xgb

        if not self._is_loaded:
            raise RuntimeError("Model not loaded")

        self.validate_input(X)
        X_processed = self.preprocess(X)

        # Convert to DMatrix for XGBoost
        dmatrix = xgb.DMatrix(X_processed)
        predictions = self._model.predict(dmatrix)

        return self.postprocess(predictions)

    def predict_proba(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Return prediction probabilities."""
        # For XGBoost, predict() returns probabilities for binary classification
        return self.predict(X)

    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """Get feature importance from XGBoost model."""
        if self._model is not None:
            importance = self._model.get_score(importance_type="gain")
            # Map feature indices to names
            feature_importance = {}
            for i, feature_name in enumerate(self.metadata.feature_names):
                feature_key = f"f{i}"
                if feature_key in importance:
                    feature_importance[feature_name] = importance[feature_key]
                else:
                    feature_importance[feature_name] = 0.0
            return feature_importance
        return None


class TensorFlowHokusaiModel(HokusaiModel):
    """Adapter for TensorFlow/Keras models."""

    def __init__(self, tf_model: Any, metadata: ModelMetadata):
        super().__init__(metadata)
        self._model = tf_model
        self._is_loaded = tf_model is not None

    def load(self, model_path: str) -> None:
        """Load TensorFlow model from SavedModel format."""
        import tensorflow as tf
        self._model = tf.keras.models.load_model(model_path)
        self._is_loaded = True
        logger.info(f"Loaded TensorFlow model from {model_path}")

    def predict(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Make predictions using TensorFlow model."""
        if not self._is_loaded:
            raise RuntimeError("Model not loaded")

        self.validate_input(X)
        X_processed = self.preprocess(X)
        predictions = self._model.predict(X_processed)

        return self.postprocess(predictions)

    def predict_proba(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Return prediction probabilities."""
        # For neural networks, the output is typically already probabilities
        return self.predict(X)


class DSPyHokusaiModel(HokusaiModel):
    """Adapter for DSPy (Declarative Self-Prompting) models."""

    def __init__(self, dspy_program: Any, metadata: ModelMetadata):
        super().__init__(metadata)
        self._model = dspy_program
        self._is_loaded = dspy_program is not None
        self._signatures = {}
        self._extract_signatures()

    def _extract_signatures(self) -> None:
        """Extract signatures from the DSPy program."""
        if self._model is None:
            return

        # Extract signatures from DSPy program attributes
        for attr_name in dir(self._model):
            if attr_name.startswith("_"):
                continue
            attr = getattr(self._model, attr_name)
            if hasattr(attr, "fields") or hasattr(attr, "input_fields"):
                self._signatures[attr_name] = attr

    def load(self, model_path: str) -> None:
        """Load DSPy model from file."""
        import pickle
        import json
        from pathlib import Path

        path = Path(model_path)

        if path.suffix == ".pkl":
            with open(model_path, "rb") as f:
                self._model = pickle.load(f)
        elif path.suffix == ".json":
            # For JSON, we'd need custom deserialization
            with open(model_path) as f:
                config = json.load(f)
            # This would require implementing DSPy program reconstruction from config
            raise NotImplementedError("JSON loading for DSPy models not yet implemented")
        else:
            raise ValueError(f"Unsupported file format for DSPy model: {path.suffix}")

        self._is_loaded = True
        self._extract_signatures()
        logger.info(f"Loaded DSPy model from {model_path}")

    def predict(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Make predictions using DSPy model."""
        if not self._is_loaded:
            raise RuntimeError("Model not loaded")

        # DSPy models work differently - they process text/structured inputs
        # Convert input to appropriate format for DSPy
        if isinstance(X, pd.DataFrame):
            # Assume each row is a separate input
            results = []
            for idx, row in X.iterrows():
                # Convert row to dict and call forward
                input_dict = row.to_dict()
                result = self._model.forward(**input_dict)
                results.append(self._extract_output(result))
            return np.array(results)
        else:
            # For numpy arrays, we need to know the feature mapping
            raise NotImplementedError("Direct numpy array input not supported for DSPy models")

    def predict_proba(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Return prediction probabilities."""
        # DSPy models typically don't return probabilities directly
        # This would need to be implemented based on specific DSPy program design
        raise NotImplementedError("Probability predictions not supported for DSPy models")

    def _extract_output(self, dspy_output: Any) -> Any:
        """Extract prediction from DSPy output format."""
        # DSPy outputs can be complex objects - extract the relevant field
        if hasattr(dspy_output, "completion"):
            return dspy_output.completion
        elif hasattr(dspy_output, "output"):
            return dspy_output.output
        elif isinstance(dspy_output, dict):
            # Look for common output keys
            for key in ["output", "result", "prediction", "completion"]:
                if key in dspy_output:
                    return dspy_output[key]
        return dspy_output

    def validate_input(self, X: Union[np.ndarray, pd.DataFrame]) -> bool:
        """Validate input data format for DSPy models."""
        if isinstance(X, pd.DataFrame):
            # For DSPy, we need to check if columns match expected signature inputs
            if self._signatures:
                # Get the first signature's expected inputs
                first_sig = next(iter(self._signatures.values()))
                if hasattr(first_sig, "input_fields"):
                    required_fields = list(first_sig.input_fields.keys())
                    missing_fields = set(required_fields) - set(X.columns)
                    if missing_fields:
                        raise ValueError(f"Missing required input fields: {missing_fields}")
            return True
        else:
            raise ValueError("DSPy models require pandas DataFrame input with named columns")

    def get_signatures(self) -> Dict[str, Any]:
        """Get all signatures defined in the DSPy program."""
        return self._signatures

    def explain_prediction(self, X: Union[np.ndarray, pd.DataFrame],
                         idx: int = 0) -> Optional[Dict[str, Any]]:
        """Explain a DSPy prediction by showing the reasoning chain."""
        if not isinstance(X, pd.DataFrame):
            raise ValueError("DSPy explanations require DataFrame input")

        # Get single input
        input_row = X.iloc[idx].to_dict()

        # Run forward with trace enabled (if supported)
        if hasattr(self._model, "forward_with_trace"):
            result, trace = self._model.forward_with_trace(**input_row)
            return {
                "input": input_row,
                "output": self._extract_output(result),
                "trace": trace,
                "signatures_used": list(self._signatures.keys())
            }
        else:
            # Basic explanation without trace
            result = self._model.forward(**input_row)
            return {
                "input": input_row,
                "output": self._extract_output(result),
                "signatures_used": list(self._signatures.keys())
            }


class ModelFactory:
    """Factory for creating HokusaiModel instances."""

    _model_types = {
        "sklearn": SklearnHokusaiModel,
        "xgboost": XGBoostHokusaiModel,
        "tensorflow": TensorFlowHokusaiModel,
        "dspy": DSPyHokusaiModel,
    }

    @classmethod
    def create_model(cls, model_type: str,
                    model_instance: Any,
                    metadata: ModelMetadata) -> HokusaiModel:
        """Create a HokusaiModel instance based on model type.
        
        Args:
            model_type: Type of model ('sklearn', 'xgboost', 'tensorflow')
            model_instance: The actual model instance
            metadata: Model metadata
            
        Returns:
            HokusaiModel instance

        """
        if model_type not in cls._model_types:
            raise ValueError(f"Unsupported model type: {model_type}")

        model_class = cls._model_types[model_type]
        return model_class(model_instance, metadata)

    @classmethod
    def register_model_type(cls, model_type: str,
                          model_class: type) -> None:
        """Register a new model type.
        
        Args:
            model_type: Name of the model type
            model_class: Class that implements HokusaiModel

        """
        if not issubclass(model_class, HokusaiModel):
            raise ValueError("Model class must inherit from HokusaiModel")

        cls._model_types[model_type] = model_class
        logger.info(f"Registered new model type: {model_type}")


def compute_feature_hash(features: Union[np.ndarray, pd.DataFrame]) -> str:
    """Compute a hash of input features for caching.
    
    Args:
        features: Input features
        
    Returns:
        SHA256 hash of the features

    """
    if isinstance(features, pd.DataFrame):
        features = features.values

    # Convert to bytes and compute hash
    feature_bytes = features.tobytes()
    return hashlib.sha256(feature_bytes).hexdigest()


def validate_model_compatibility(model_a: HokusaiModel,
                               model_b: HokusaiModel) -> bool:
    """Check if two models are compatible for A/B testing.
    
    Args:
        model_a: First model
        model_b: Second model
        
    Returns:
        True if models are compatible
        
    Raises:
        ValueError: If models are incompatible

    """
    # Check model types
    if model_a.metadata.model_type != model_b.metadata.model_type:
        raise ValueError(
            f"Model types don't match: {model_a.metadata.model_type} vs "
            f"{model_b.metadata.model_type}"
        )

    # Check feature compatibility
    features_a = set(model_a.get_required_features())
    features_b = set(model_b.get_required_features())

    if features_a != features_b:
        diff_a = features_a - features_b
        diff_b = features_b - features_a
        raise ValueError(
            f"Feature mismatch. A has extra: {diff_a}, B has extra: {diff_b}"
        )

    # Check model family
    if model_a.metadata.model_family != model_b.metadata.model_family:
        logger.warning(
            f"Different model families: {model_a.metadata.model_family} vs "
            f"{model_b.metadata.model_family}"
        )

    return True
