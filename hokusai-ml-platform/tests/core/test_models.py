"""Tests for model abstraction layer."""

import pytest

# Since we're writing tests first, we'll import from the expected module location
# These imports will fail until we implement the actual classes
from hokusai.core.models import HokusaiModel, ModelFactory, ModelType


class TestHokusaiModel:
    """Test cases for HokusaiModel base class."""

    def test_model_initialization(self) -> None:
        """Test that HokusaiModel can be initialized with required attributes."""
        # Create a concrete implementation for testing
        class TestModel(HokusaiModel):
            def predict(self, data):
                return {}
            def load(self, path: str):
                pass
            def save(self, path: str):
                pass

        model = TestModel(
            model_id="test-model-001",
            model_type=ModelType.CLASSIFICATION,
            version="1.0.0",
            metadata={"author": "test", "description": "Test model"}
        )

        assert model.model_id == "test-model-001"
        assert model.model_type == ModelType.CLASSIFICATION
        assert model.version == "1.0.0"
        assert model.metadata["author"] == "test"

    def test_model_predict_abstract(self) -> None:
        """Test that predict method must be implemented by subclasses."""
        # Create a partial implementation that doesn't implement predict
        class PartialModel(HokusaiModel):
            def load(self, path: str):
                pass
            def save(self, path: str):
                pass

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            model = PartialModel(
                model_id="test-model-001",
                model_type=ModelType.CLASSIFICATION,
                version="1.0.0"
            )

    def test_model_concrete_implementation(self) -> None:
        """Test concrete model implementation."""
        class ConcreteModel(HokusaiModel):
            def predict(self, data):
                return {"result": "predicted"}
            def load(self, path: str):
                return f"loaded from {path}"
            def save(self, path: str):
                return f"saved to {path}"

        model = ConcreteModel(
            model_id="test-model-001",
            model_type=ModelType.CLASSIFICATION,
            version="1.0.0"
        )

        assert model.predict({}) == {"result": "predicted"}
        assert model.load("/path") == "loaded from /path"
        assert model.save("/path") == "saved to /path"

    def test_model_get_metrics(self) -> None:
        """Test that models can return their performance metrics."""
        class TestModel(HokusaiModel):
            def predict(self, data):
                return {}
            def load(self, path: str):
                pass
            def save(self, path: str):
                pass

        model = TestModel(
            model_id="test-model-001",
            model_type=ModelType.CLASSIFICATION,
            version="1.0.0",
            metrics={"accuracy": 0.95, "f1_score": 0.93}
        )

        metrics = model.get_metrics()
        assert metrics["accuracy"] == 0.95
        assert metrics["f1_score"] == 0.93


class TestModelFactory:
    """Test cases for ModelFactory."""

    def test_create_classification_model(self) -> None:
        """Test creating a classification model through factory."""
        model = ModelFactory.create_model(
            model_type=ModelType.CLASSIFICATION,
            model_id="clf-001",
            version="1.0.0",
            config={"n_classes": 3}
        )

        assert model.model_type == ModelType.CLASSIFICATION
        assert model.model_id == "clf-001"
        assert model.version == "1.0.0"

    def test_create_regression_model(self) -> None:
        """Test creating a regression model through factory."""
        model = ModelFactory.create_model(
            model_type=ModelType.REGRESSION,
            model_id="reg-001",
            version="1.0.0",
            config={"output_dim": 1}
        )

        assert model.model_type == ModelType.REGRESSION
        assert model.model_id == "reg-001"

    def test_create_custom_model(self) -> None:
        """Test creating a custom model type through factory."""
        model = ModelFactory.create_model(
            model_type=ModelType.CUSTOM,
            model_id="custom-001",
            version="1.0.0",
            config={"model_class": "LeadScoringModel"}
        )

        assert model.model_type == ModelType.CUSTOM
        assert model.model_id == "custom-001"

    def test_register_custom_model_class(self) -> None:
        """Test registering a custom model class with the factory."""
        class CustomTestModel(HokusaiModel):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)

            def predict(self, data):
                return {"prediction": "custom"}

            def load(self, path: str):
                pass

            def save(self, path: str):
                pass

        ModelFactory.register_model_class("custom_test_type", CustomTestModel)

        model = ModelFactory.create_model(
            model_type="custom_test_type",
            model_id="custom-002",
            version="1.0.0"
        )

        assert isinstance(model, CustomTestModel)
        assert model.predict({}) == {"prediction": "custom"}

    def test_create_unknown_model_type_raises_error(self) -> None:
        """Test that creating unknown model type raises appropriate error."""
        with pytest.raises(ValueError, match="Unknown model type"):
            ModelFactory.create_model(
                model_type="unknown_type",
                model_id="unknown-001",
                version="1.0.0"
            )

    def test_model_serialization(self) -> None:
        """Test that models can be serialized and deserialized."""
        model = ModelFactory.create_model(
            model_type=ModelType.CLASSIFICATION,
            model_id="ser-001",
            version="1.0.0",
            metadata={"test": "data"}
        )

        serialized = model.to_dict()
        assert serialized["model_id"] == "ser-001"
        assert serialized["model_type"] == ModelType.CLASSIFICATION
        assert serialized["version"] == "1.0.0"
        assert serialized["metadata"]["test"] == "data"

        # Test deserialization
        restored = ModelFactory.from_dict(serialized)
        assert restored.model_id == model.model_id
        assert restored.model_type == model.model_type
        assert restored.version == model.version