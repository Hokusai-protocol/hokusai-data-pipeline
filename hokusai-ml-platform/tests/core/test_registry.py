"""Tests for Model Registry functionality."""
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from hokusai.core.models import HokusaiModel, ModelType
from hokusai.core.registry import ModelRegistry, ModelRegistryEntry, RegistryException


class TestModelRegistry:
    """Test cases for ModelRegistry."""

    @pytest.fixture
    def mock_mlflow(self):
        """Mock MLflow for testing."""
        with patch("mlflow.set_tracking_uri") as mock_set_uri, \
             patch("mlflow.MlflowClient") as mock_client:
            yield mock_set_uri, mock_client

    @pytest.fixture
    def registry(self, mock_mlflow):
        """Create a ModelRegistry instance with mocked MLflow."""
        return ModelRegistry(tracking_uri="http://test-mlflow:5000")

    def test_registry_initialization(self, mock_mlflow) -> None:
        """Test ModelRegistry initialization with MLflow tracking URI."""
        mock_set_uri, mock_client = mock_mlflow
        registry = ModelRegistry(tracking_uri="http://test-mlflow:5000")

        mock_set_uri.assert_called_once_with("http://test-mlflow:5000")
        assert registry.tracking_uri == "http://test-mlflow:5000"
        assert registry.client is not None

    def test_register_baseline_model(self, registry) -> None:
        """Test registering a baseline model."""
        mock_model = Mock(spec=HokusaiModel)
        mock_model.model_id = "baseline-001"
        mock_model.model_type = ModelType.CLASSIFICATION
        mock_model.version = "1.0.0"
        mock_model.get_metrics.return_value = {"accuracy": 0.85}

        with patch.object(registry.client, "create_registered_model") as mock_create, \
             patch.object(registry.client, "create_model_version") as mock_version, \
             patch.object(registry.client, "set_model_version_tag") as mock_tag:

            mock_version.return_value = Mock(version="1")

            entry = registry.register_baseline(
                model=mock_model,
                model_type="lead_scoring",
                metadata={"dataset": "initial_training"}
            )

            assert entry.model_id == "baseline-001"
            assert entry.model_type == "lead_scoring"
            assert entry.is_baseline is True
            assert entry.baseline_id is None
            assert entry.metrics["accuracy"] == 0.85

            mock_create.assert_called_once()
            mock_version.assert_called_once()
            mock_tag.assert_called()

    def test_register_improved_model(self, registry) -> None:
        """Test registering an improved model with baseline reference."""
        mock_baseline = Mock(spec=HokusaiModel)
        mock_baseline.model_id = "baseline-001"
        mock_baseline.get_metrics.return_value = {"accuracy": 0.85}

        mock_improved = Mock(spec=HokusaiModel)
        mock_improved.model_id = "improved-001"
        mock_improved.model_type = ModelType.CLASSIFICATION
        mock_improved.version = "2.0.0"
        mock_improved.get_metrics.return_value = {"accuracy": 0.92}

        delta_metrics = {"accuracy_improvement": 0.07}
        contributor_address = "0xAbC123...789"

        with patch.object(registry, "get_model_by_id") as mock_get, \
             patch.object(registry.client, "create_model_version") as mock_version, \
             patch.object(registry.client, "set_model_version_tag") as mock_tag:

            mock_get.return_value = ModelRegistryEntry(
                model_id="baseline-001",
                model_type="lead_scoring",
                version="1.0.0",
                is_baseline=True,
                metrics={"accuracy": 0.85}
            )
            mock_version.return_value = Mock(version="2")

            entry = registry.register_improved_model(
                model=mock_improved,
                baseline_id="baseline-001",
                delta_metrics=delta_metrics,
                contributor=contributor_address
            )

            assert entry.model_id == "improved-001"
            assert entry.baseline_id == "baseline-001"
            assert entry.is_baseline is False
            assert entry.delta_metrics["accuracy_improvement"] == 0.07
            assert entry.contributor_address == contributor_address
            assert entry.metrics["accuracy"] == 0.92

    def test_get_model_lineage(self, registry) -> None:
        """Test retrieving complete model lineage."""
        lineage_data = [
            {
                "model_id": "baseline-001",
                "baseline_id": None,
                "version": "1.0.0",
                "metrics": {"accuracy": 0.85},
                "timestamp": datetime.now().isoformat()
            },
            {
                "model_id": "improved-001",
                "baseline_id": "baseline-001",
                "version": "2.0.0",
                "metrics": {"accuracy": 0.90},
                "delta_metrics": {"accuracy_improvement": 0.05},
                "contributor_address": "0xAbC123",
                "timestamp": datetime.now().isoformat()
            },
            {
                "model_id": "improved-002",
                "baseline_id": "improved-001",
                "version": "3.0.0",
                "metrics": {"accuracy": 0.92},
                "delta_metrics": {"accuracy_improvement": 0.02},
                "contributor_address": "0xDef456",
                "timestamp": datetime.now().isoformat()
            }
        ]

        with patch.object(registry, "_fetch_lineage_data") as mock_fetch:
            mock_fetch.return_value = lineage_data

            lineage = registry.get_model_lineage("improved-002")

            assert len(lineage.entries) == 3
            assert lineage.model_id == "improved-002"
            assert lineage.entries[0]["model_id"] == "baseline-001"
            assert lineage.entries[-1]["model_id"] == "improved-002"
            assert lineage.total_improvement == 0.07

    def test_get_model_by_id(self, registry) -> None:
        """Test retrieving a model by its ID."""
        with patch.object(registry.client, "search_model_versions") as mock_search:
            mock_version = Mock()
            mock_version.tags = {
                "model_id": "test-001",
                "model_type": "lead_scoring",
                "is_baseline": "true",
                "metrics": '{"accuracy": 0.85}'
            }
            mock_search.return_value = [mock_version]

            entry = registry.get_model_by_id("test-001")

            assert entry.model_id == "test-001"
            assert entry.model_type == "lead_scoring"
            assert entry.is_baseline is True
            assert entry.metrics["accuracy"] == 0.85

    def test_get_nonexistent_model_raises_error(self, registry) -> None:
        """Test that getting non-existent model raises appropriate error."""
        with patch.object(registry.client, "search_model_versions") as mock_search:
            mock_search.return_value = []

            with pytest.raises(RegistryException, match="Model not found"):
                registry.get_model_by_id("nonexistent-001")

    def test_list_models_by_type(self, registry) -> None:
        """Test listing all models of a specific type."""
        with patch.object(registry.client, "search_model_versions") as mock_search:
            mock_versions = [
                Mock(tags={
                    "model_id": "model-001",
                    "model_type": "lead_scoring",
                    "version": "1.0.0"
                }),
                Mock(tags={
                    "model_id": "model-002",
                    "model_type": "lead_scoring",
                    "version": "2.0.0"
                })
            ]
            mock_search.return_value = mock_versions

            models = registry.list_models_by_type("lead_scoring")

            assert len(models) == 2
            assert all(m.model_type == "lead_scoring" for m in models)

    def test_get_latest_model_version(self, registry) -> None:
        """Test getting the latest version of a model type."""
        with patch.object(registry.client, "get_latest_versions") as mock_latest:
            mock_version = Mock()
            mock_version.version = "3"
            mock_version.tags = {
                "model_id": "latest-001",
                "model_type": "lead_scoring",
                "version": "3.0.0"
            }
            mock_latest.return_value = [mock_version]

            latest = registry.get_latest_model("lead_scoring")

            assert latest.model_id == "latest-001"
            assert latest.version == "3.0.0"

    def test_model_rollback(self, registry) -> None:
        """Test rolling back to a previous model version."""
        with patch.object(registry.client, "transition_model_version_stage") as mock_transition, \
             patch.object(registry, "get_model_by_id") as mock_get:

            mock_get.return_value = ModelRegistryEntry(
                model_id="model-001",
                model_type="lead_scoring",
                version="2.0.0",
                mlflow_version="2"
            )

            success = registry.rollback_model("lead_scoring", "model-001")

            assert success is True
            mock_transition.assert_called()

    def test_delete_model_version(self, registry) -> None:
        """Test deleting a specific model version."""
        with patch.object(registry.client, "delete_model_version") as mock_delete, \
             patch.object(registry, "get_model_by_id") as mock_get:

            mock_get.return_value = ModelRegistryEntry(
                model_id="model-001",
                model_type="lead_scoring",
                version="2.0.0",
                mlflow_version="2"
            )

            success = registry.delete_model_version("model-001")

            assert success is True
            mock_delete.assert_called_once()
