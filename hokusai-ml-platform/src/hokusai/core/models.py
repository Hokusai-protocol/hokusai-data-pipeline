"""Model abstraction layer for Hokusai ML Platform."""
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Type, Union


class ModelType(str, Enum):
    """Supported model types."""

    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    CUSTOM = "custom"


class HokusaiModel(ABC):
    """Base class for all Hokusai models."""

    def __init__(
        self,
        model_id: str,
        model_type: Union[ModelType, str],
        version: str,
        metadata: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, float]] = None,
        **kwargs,
    ) -> None:
        self.model_id = model_id
        self.model_type = model_type
        self.version = version
        self.metadata = metadata or {}
        self.metrics = metrics or {}
        self.created_at = datetime.utcnow()

        # Store any additional attributes
        for key, value in kwargs.items():
            setattr(self, key, value)

    @abstractmethod
    def predict(self, data: Any) -> Dict[str, Any]:
        """Make prediction on input data."""
        raise NotImplementedError("Subclasses must implement predict method")

    @abstractmethod
    def load(self, path: str) -> None:
        """Load model from disk."""
        raise NotImplementedError("Subclasses must implement load method")

    @abstractmethod
    def save(self, path: str) -> None:
        """Save model to disk."""
        raise NotImplementedError("Subclasses must implement save method")

    def get_metrics(self) -> Dict[str, float]:
        """Get model performance metrics."""
        return self.metrics.copy()

    def get_memory_usage(self) -> float:
        """Get estimated memory usage in MB."""
        # Default implementation - subclasses can override
        return 100.0  # Default 100MB

    def batch_predict(self, data_list: list) -> list:
        """Make predictions on a batch of data."""
        # Default implementation - process one by one
        return [self.predict(data) for data in data_list]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize model metadata to dictionary."""
        return {
            "model_id": self.model_id,
            "model_type": self.model_type.value
            if isinstance(self.model_type, ModelType)
            else self.model_type,
            "version": self.version,
            "metadata": self.metadata,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat(),
        }


class ClassificationModel(HokusaiModel):
    """Base classification model implementation."""

    def __init__(self, n_classes: int = 2, **kwargs) -> None:
        super().__init__(model_type=ModelType.CLASSIFICATION, **kwargs)
        self.n_classes = n_classes

    def predict(self, data: Any) -> Dict[str, Any]:
        """Placeholder prediction for classification."""
        # This is a placeholder - real implementation would use actual model
        return {
            "prediction": 0,
            "probabilities": [0.5] * self.n_classes,
            "model_type": "classification",
        }

    def load(self, path: str) -> None:
        """Load classification model."""
        # Placeholder implementation
        pass

    def save(self, path: str) -> None:
        """Save classification model."""
        # Placeholder implementation
        pass


class RegressionModel(HokusaiModel):
    """Base regression model implementation."""

    def __init__(self, output_dim: int = 1, **kwargs) -> None:
        super().__init__(model_type=ModelType.REGRESSION, **kwargs)
        self.output_dim = output_dim

    def predict(self, data: Any) -> Dict[str, Any]:
        """Placeholder prediction for regression."""
        return {"prediction": 0.0, "confidence_interval": [0.0, 1.0], "model_type": "regression"}

    def load(self, path: str) -> None:
        """Load regression model."""
        pass

    def save(self, path: str) -> None:
        """Save regression model."""
        pass


class CustomModel(HokusaiModel):
    """Custom model implementation for specialized use cases."""

    def __init__(self, model_class: str, **kwargs) -> None:
        super().__init__(model_type=ModelType.CUSTOM, **kwargs)
        self.model_class = model_class

    def predict(self, data: Any) -> Dict[str, Any]:
        """Custom prediction logic."""
        return {"prediction": "custom", "model_class": self.model_class, "model_type": "custom"}

    def load(self, path: str) -> None:
        """Load custom model."""
        pass

    def save(self, path: str) -> None:
        """Save custom model."""
        pass


class ModelFactory:
    """Factory for creating model instances."""

    _model_classes: Dict[str, Type[HokusaiModel]] = {
        ModelType.CLASSIFICATION: ClassificationModel,
        ModelType.REGRESSION: RegressionModel,
        ModelType.CUSTOM: CustomModel,
    }

    @classmethod
    def create_model(
        cls,
        model_type: Union[ModelType, str],
        model_id: str,
        version: str,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> HokusaiModel:
        """Create a model instance based on type."""
        config = config or {}

        # Convert string to ModelType if necessary
        if isinstance(model_type, str):
            if model_type in cls._model_classes:
                model_type_enum = model_type
            else:
                # Check if it's a valid ModelType value
                try:
                    model_type_enum = ModelType(model_type)
                except ValueError:
                    # It's a custom registered type
                    if model_type not in cls._model_classes:
                        raise ValueError(f"Unknown model type: {model_type}")
                    model_type_enum = model_type
        else:
            model_type_enum = model_type

        # Get the appropriate model class
        model_class = cls._model_classes.get(model_type_enum)
        if not model_class:
            raise ValueError(f"Unknown model type: {model_type}")

        # Create model instance
        if model_type_enum == ModelType.CLASSIFICATION:
            return model_class(
                model_id=model_id,
                version=version,
                n_classes=config.get("n_classes", 2),
                metadata=metadata,
                **kwargs,
            )
        elif model_type_enum == ModelType.REGRESSION:
            return model_class(
                model_id=model_id,
                version=version,
                output_dim=config.get("output_dim", 1),
                metadata=metadata,
                **kwargs,
            )
        elif model_type_enum == ModelType.CUSTOM:
            return model_class(
                model_id=model_id,
                version=version,
                model_class=config.get("model_class", "CustomModel"),
                metadata=metadata,
                **kwargs,
            )
        else:
            # For custom registered types
            return model_class(
                model_id=model_id,
                model_type=model_type,
                version=version,
                metadata=metadata,
                **config,
                **kwargs,
            )

    @classmethod
    def register_model_class(cls, model_type: str, model_class: Type[HokusaiModel]) -> None:
        """Register a custom model class."""
        if not issubclass(model_class, HokusaiModel):
            raise ValueError("Model class must inherit from HokusaiModel")
        cls._model_classes[model_type] = model_class

    @classmethod
    def from_dict(cls, model_dict: Dict[str, Any]) -> HokusaiModel:
        """Create model from dictionary representation."""
        model_type = model_dict.get("model_type")
        model_id = model_dict.get("model_id")
        version = model_dict.get("version")
        metadata = model_dict.get("metadata", {})
        metrics = model_dict.get("metrics", {})

        if not all([model_type, model_id, version]):
            raise ValueError("model_type, model_id, and version are required")

        return cls.create_model(
            model_type=model_type,
            model_id=model_id,
            version=version,
            metadata=metadata,
            metrics=metrics,
        )
