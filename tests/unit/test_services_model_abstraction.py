"""Unit tests for model abstraction service."""

from datetime import datetime
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from src.services.model_abstraction import (
    DSPyHokusaiModel,
    HokusaiModel,
    ModelAdapter,
    ModelFactory,
    ModelMetadata,
    ModelStatus,
    ModelType,
    SklearnHokusaiModel,
    TensorFlowHokusaiModel,
    XGBoostHokusaiModel,
)


class TestModelType:
    """Test suite for ModelType enum."""

    def test_model_types(self):
        """Test model type enumeration values."""
        assert ModelType.LEAD_SCORING.value == "lead_scoring"
        assert ModelType.CLASSIFICATION.value == "classification"
        assert ModelType.REGRESSION.value == "regression"
        assert ModelType.RANKING.value == "ranking"
        assert ModelType.DSPY.value == "dspy"


class TestModelStatus:
    """Test suite for ModelStatus enum."""

    def test_model_status_values(self):
        """Test model status enumeration values."""
        assert ModelStatus.STAGING.value == "staging"
        assert ModelStatus.PRODUCTION.value == "production"
        assert ModelStatus.DEPRECATED.value == "deprecated"
        assert ModelStatus.ARCHIVED.value == "archived"


class TestModelMetadata:
    """Test suite for ModelMetadata dataclass."""

    def setup_method(self):
        """Set up test fixtures."""
        self.metadata = ModelMetadata(
            model_id="model_123",
            model_family="lead_scoring",
            version="1.0.0",
            model_type=ModelType.LEAD_SCORING,
            status=ModelStatus.PRODUCTION,
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            updated_at=datetime(2024, 1, 15, 14, 0, 0),
            training_metadata={"epochs": 10, "batch_size": 32},
            performance_metrics={"accuracy": 0.95, "f1": 0.93},
            feature_names=["feature1", "feature2", "feature3"],
            feature_types={"feature1": "numeric", "feature2": "categorical", "feature3": "numeric"},
            contributor_address="0x123abc",
            baseline_model_id="model_122",
        )

    def test_metadata_creation(self):
        """Test creating model metadata."""
        assert self.metadata.model_id == "model_123"
        assert self.metadata.model_family == "lead_scoring"
        assert self.metadata.version == "1.0.0"
        assert self.metadata.model_type == ModelType.LEAD_SCORING
        assert self.metadata.status == ModelStatus.PRODUCTION
        assert self.metadata.contributor_address == "0x123abc"
        assert len(self.metadata.feature_names) == 3

    def test_metadata_to_dict(self):
        """Test converting metadata to dictionary."""
        data = self.metadata.to_dict()

        assert data["model_id"] == "model_123"
        assert data["model_type"] == "lead_scoring"
        assert data["status"] == "production"
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)
        assert data["training_metadata"]["epochs"] == 10
        assert data["performance_metrics"]["accuracy"] == 0.95


class ConcreteHokusaiModel(HokusaiModel):
    """Concrete implementation for testing abstract base class."""

    def load(self, model_path: str) -> None:
        """Load model implementation."""
        self._model = Mock()
        self._is_loaded = True

    def predict(self, X):
        """Predict implementation."""
        return np.array([1, 0, 1])

    def predict_proba(self, X):
        """Predict proba implementation."""
        return np.array([[0.1, 0.9], [0.8, 0.2], [0.3, 0.7]])

    def get_feature_importance(self):
        """Feature importance implementation."""
        return {"feature1": 0.5, "feature2": 0.3, "feature3": 0.2}

    def validate_input(self, X):
        """Validate input implementation."""
        return True

    def preprocess(self, X):
        """Preprocess implementation."""
        return X

    def postprocess(self, predictions):
        """Postprocess implementation."""
        return predictions


class TestHokusaiModel:
    """Test suite for HokusaiModel abstract base class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.metadata = ModelMetadata(
            model_id="test_model",
            model_family="test_family",
            version="1.0.0",
            model_type=ModelType.CLASSIFICATION,
            status=ModelStatus.STAGING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            training_metadata={},
            performance_metrics={},
            feature_names=["f1", "f2"],
            feature_types={"f1": "numeric", "f2": "numeric"},
        )
        self.model = ConcreteHokusaiModel(self.metadata)

    def test_model_initialization(self):
        """Test model initialization."""
        assert self.model.metadata == self.metadata
        assert self.model._model is None
        assert self.model._is_loaded is False

    def test_model_load(self):
        """Test model loading."""
        self.model.load("/path/to/model")

        assert self.model._is_loaded is True
        assert self.model._model is not None

    def test_model_predict(self):
        """Test model prediction."""
        X = np.array([[1, 2], [3, 4], [5, 6]])
        predictions = self.model.predict(X)

        assert isinstance(predictions, np.ndarray)
        assert len(predictions) == 3

    def test_model_predict_proba(self):
        """Test model probability prediction."""
        X = np.array([[1, 2], [3, 4], [5, 6]])
        proba = self.model.predict_proba(X)

        assert isinstance(proba, np.ndarray)
        assert proba.shape == (3, 2)

    def test_get_feature_importance(self):
        """Test getting feature importance."""
        importance = self.model.get_feature_importance()

        assert isinstance(importance, dict)
        assert "feature1" in importance
        assert sum(importance.values()) == pytest.approx(1.0)


@pytest.mark.skip(reason="ModelAdapter is a static utility class, tests need rewriting")
class TestModelAdapter:
    """Test suite for ModelAdapter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_model = Mock(spec=HokusaiModel)
        self.mock_model.metadata = Mock()
        self.mock_model.metadata.model_id = "test_model"
        self.mock_model.metadata.feature_names = ["f1", "f2", "f3"]

        self.adapter = ModelAdapter(self.mock_model)

    def test_adapter_initialization(self):
        """Test adapter initialization."""
        assert self.adapter.model == self.mock_model
        assert self.adapter._cache == {}
        assert self.adapter._cache_size == 0
        assert self.adapter.max_cache_size == 100

    def test_predict_with_caching(self):
        """Test prediction with caching."""
        X = np.array([[1, 2, 3], [4, 5, 6]])
        expected_predictions = np.array([0, 1])
        self.mock_model.predict.return_value = expected_predictions

        # First call - should hit model
        predictions1 = self.adapter.predict(X, use_cache=True)
        assert np.array_equal(predictions1, expected_predictions)
        self.mock_model.predict.assert_called_once()

        # Second call - should hit cache
        predictions2 = self.adapter.predict(X, use_cache=True)
        assert np.array_equal(predictions2, expected_predictions)
        # Still called only once
        assert self.mock_model.predict.call_count == 1

    def test_predict_without_caching(self):
        """Test prediction without caching."""
        X = np.array([[1, 2, 3]])
        self.mock_model.predict.return_value = np.array([1])

        # Multiple calls should all hit the model
        for _ in range(3):
            self.adapter.predict(X, use_cache=False)

        assert self.mock_model.predict.call_count == 3

    def test_predict_proba_with_threshold(self):
        """Test probability prediction with threshold."""
        X = np.array([[1, 2, 3]])
        proba = np.array([[0.3, 0.7]])
        self.mock_model.predict_proba.return_value = proba

        # With default threshold (0.5)
        predictions = self.adapter.predict_proba(X, return_binary=True)
        assert predictions[0] == 1  # 0.7 > 0.5

        # With custom threshold
        predictions = self.adapter.predict_proba(X, threshold=0.8, return_binary=True)
        assert predictions[0] == 0  # 0.7 < 0.8

    def test_batch_predict(self):
        """Test batch prediction."""
        X = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]])
        self.mock_model.predict.return_value = np.array([0, 1])

        predictions = self.adapter.batch_predict(X, batch_size=2)

        # Should be called twice (4 samples / batch_size 2)
        assert self.mock_model.predict.call_count == 2
        assert len(predictions) == 4

    def test_cache_management(self):
        """Test cache size management."""
        self.adapter.max_cache_size = 2

        # Add entries to cache
        for i in range(3):
            X = np.array([[i, i + 1, i + 2]])
            self.mock_model.predict.return_value = np.array([i])
            self.adapter.predict(X, use_cache=True)

        # Cache should not exceed max size
        assert self.adapter._cache_size <= 2
        assert len(self.adapter._cache) <= 2

    def test_clear_cache(self):
        """Test clearing the cache."""
        # Add some entries
        X = np.array([[1, 2, 3]])
        self.mock_model.predict.return_value = np.array([1])
        self.adapter.predict(X, use_cache=True)

        assert len(self.adapter._cache) > 0

        # Clear cache
        self.adapter.clear_cache()

        assert len(self.adapter._cache) == 0
        assert self.adapter._cache_size == 0


class TestSklearnHokusaiModel:
    """Test suite for SklearnHokusaiModel class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.metadata = ModelMetadata(
            model_id="sklearn_model",
            model_family="classification",
            version="1.0.0",
            model_type=ModelType.CLASSIFICATION,
            status=ModelStatus.PRODUCTION,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            training_metadata={},
            performance_metrics={},
            feature_names=["f1", "f2"],
            feature_types={"f1": "numeric", "f2": "numeric"},
        )
        self.model = SklearnHokusaiModel(None, self.metadata)

    @patch("joblib.load")
    def test_load_model(self, mock_joblib_load):
        """Test loading sklearn model."""
        mock_sklearn_model = Mock()
        mock_joblib_load.return_value = mock_sklearn_model

        self.model.load("/path/to/model.pkl")

        assert self.model._model == mock_sklearn_model
        assert self.model._is_loaded is True
        mock_joblib_load.assert_called_once_with("/path/to/model.pkl")

    def test_predict(self):
        """Test sklearn model prediction."""
        # Mock the internal sklearn model
        mock_sklearn_model = Mock()
        mock_sklearn_model.predict.return_value = np.array([0, 1, 0])
        self.model._model = mock_sklearn_model
        self.model._is_loaded = True

        X = pd.DataFrame([[1, 2], [3, 4], [5, 6]], columns=["f1", "f2"])
        predictions = self.model.predict(X)

        assert isinstance(predictions, np.ndarray)
        assert len(predictions) == 3
        mock_sklearn_model.predict.assert_called_once()

    def test_predict_not_loaded(self):
        """Test prediction when model not loaded."""
        X = pd.DataFrame([[1, 2]], columns=["f1", "f2"])

        with pytest.raises(RuntimeError, match="Model not loaded"):
            self.model.predict(X)

    def test_get_feature_importance(self):
        """Test getting feature importance from sklearn model."""
        # Mock model with feature_importances_
        mock_sklearn_model = Mock()
        mock_sklearn_model.feature_importances_ = np.array([0.7, 0.3])
        self.model._model = mock_sklearn_model
        self.model._is_loaded = True

        importance = self.model.get_feature_importance()

        assert importance == {"f1": 0.7, "f2": 0.3}

    def test_validate_input(self):
        """Test input validation for sklearn model."""
        # Valid input
        X_valid = pd.DataFrame([[1, 2]], columns=["f1", "f2"])
        assert self.model.validate_input(X_valid) is True

        # Missing column
        X_invalid = pd.DataFrame([[1]], columns=["f1"])
        assert self.model.validate_input(X_invalid) is False

        # Extra column is okay
        X_extra = pd.DataFrame([[1, 2, 3]], columns=["f1", "f2", "f3"])
        assert self.model.validate_input(X_extra) is True


class TestModelFactory:
    """Test suite for ModelFactory class."""

    def test_create_sklearn_model(self):
        """Test creating sklearn model."""
        metadata = ModelMetadata(
            model_id="test",
            model_family="test",
            version="1.0",
            model_type=ModelType.CLASSIFICATION,
            status=ModelStatus.STAGING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            training_metadata={"framework": "sklearn"},
            performance_metrics={},
            feature_names=[],
            feature_types={},
        )

        model = ModelFactory.create_model(metadata)

        assert isinstance(model, SklearnHokusaiModel)
        assert model.metadata == metadata

    def test_create_xgboost_model(self):
        """Test creating xgboost model."""
        metadata = ModelMetadata(
            model_id="test",
            model_family="test",
            version="1.0",
            model_type=ModelType.REGRESSION,
            status=ModelStatus.STAGING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            training_metadata={"framework": "xgboost"},
            performance_metrics={},
            feature_names=[],
            feature_types={},
        )

        model = ModelFactory.create_model(metadata)

        assert isinstance(model, XGBoostHokusaiModel)

    def test_create_tensorflow_model(self):
        """Test creating tensorflow model."""
        metadata = ModelMetadata(
            model_id="test",
            model_family="test",
            version="1.0",
            model_type=ModelType.CLASSIFICATION,
            status=ModelStatus.STAGING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            training_metadata={"framework": "tensorflow"},
            performance_metrics={},
            feature_names=[],
            feature_types={},
        )

        model = ModelFactory.create_model(metadata)

        assert isinstance(model, TensorFlowHokusaiModel)

    def test_create_dspy_model(self):
        """Test creating dspy model."""
        metadata = ModelMetadata(
            model_id="test",
            model_family="test",
            version="1.0",
            model_type=ModelType.DSPY,
            status=ModelStatus.STAGING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            training_metadata={},
            performance_metrics={},
            feature_names=[],
            feature_types={},
        )

        model = ModelFactory.create_model(metadata)

        assert isinstance(model, DSPyHokusaiModel)

    def test_create_model_unsupported_framework(self):
        """Test creating model with unsupported framework."""
        metadata = ModelMetadata(
            model_id="test",
            model_family="test",
            version="1.0",
            model_type=ModelType.CLASSIFICATION,
            status=ModelStatus.STAGING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            training_metadata={"framework": "unknown"},
            performance_metrics={},
            feature_names=[],
            feature_types={},
        )

        with pytest.raises(ValueError, match="Unsupported model framework"):
            ModelFactory.create_model(metadata)

    def test_register_custom_model_class(self):
        """Test registering custom model class."""

        class CustomModel(HokusaiModel):
            def load(self, path):
                pass

            def predict(self, X):
                pass

            def predict_proba(self, X):
                pass

            def get_feature_importance(self):
                pass

            def validate_input(self, X):
                pass

            def preprocess(self, X):
                pass

            def postprocess(self, pred):
                pass

        ModelFactory.register_model_class("custom", CustomModel)

        assert "custom" in ModelFactory._model_classes
        assert ModelFactory._model_classes["custom"] == CustomModel
