"""Unit tests for Hokusai Model Registry service."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.services.model_registry import HokusaiModelRegistry


class TestHokusaiModelRegistry:
    """Test suite for HokusaiModelRegistry class."""

    @patch("mlflow.set_tracking_uri")
    def test_initialization(self, mock_set_tracking):
        """Test model registry initialization."""
        registry = HokusaiModelRegistry("http://test-mlflow:5000")

        assert registry.tracking_uri == "http://test-mlflow:5000"
        mock_set_tracking.assert_called_once_with("http://test-mlflow:5000")

    @patch("mlflow.set_tracking_uri")
    def test_initialization_default_uri(self, mock_set_tracking):
        """Test initialization with default URI."""
        registry = HokusaiModelRegistry()

        assert registry.tracking_uri == "http://mlflow-server:5000"

    def test_valid_model_types(self):
        """Test valid model types constant."""
        assert "lead_scoring" in HokusaiModelRegistry.VALID_MODEL_TYPES
        assert "classification" in HokusaiModelRegistry.VALID_MODEL_TYPES
        assert "regression" in HokusaiModelRegistry.VALID_MODEL_TYPES
        assert "ranking" in HokusaiModelRegistry.VALID_MODEL_TYPES

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.start_run")
    @patch("mlflow.log_params")
    @patch("mlflow.log_param")
    @patch("mlflow.pyfunc.log_model")
    @patch("mlflow.register_model")
    def test_register_baseline(
        self,
        mock_register_model,
        mock_log_model,
        mock_log_param,
        mock_log_params,
        mock_start_run,
        mock_set_tracking,
    ):
        """Test registering a baseline model."""
        # Setup mocks
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_123"
        mock_start_run.return_value.__enter__.return_value = mock_run

        mock_model_version = Mock()
        mock_model_version.version = "1"
        mock_register_model.return_value = mock_model_version

        # Create registry and model
        registry = HokusaiModelRegistry()
        mock_model = Mock()

        metadata = {"dataset": "test_dataset", "accuracy": 0.85}

        # Register baseline
        result = registry.register_baseline(mock_model, "classification", metadata)

        # Verify result
        assert result["model_id"] == "hokusai_classification_baseline"
        assert result["version"] == "1"
        assert result["run_id"] == "test_run_123"
        assert result["model_type"] == "classification"
        assert result["is_baseline"] is True

        # Verify MLflow calls
        mock_log_params.assert_called_once()
        logged_params = mock_log_params.call_args[0][0]
        assert logged_params["model_type"] == "classification"
        assert logged_params["is_baseline"] is True

        # Verify metadata logging
        mock_log_param.assert_any_call("metadata_dataset", "test_dataset")
        mock_log_param.assert_any_call("metadata_accuracy", 0.85)

        # Verify model logging
        mock_log_model.assert_called_once_with(
            artifact_path="model",
            python_model=mock_model,
            registered_model_name="hokusai_classification_baseline",
        )

    @patch("mlflow.set_tracking_uri")
    def test_register_baseline_invalid_model(self, mock_set_tracking):
        """Test registering baseline with invalid model."""
        registry = HokusaiModelRegistry()

        with pytest.raises(ValueError, match="Model cannot be None"):
            registry.register_baseline(None, "classification", {})

    @patch("mlflow.set_tracking_uri")
    def test_register_baseline_invalid_type(self, mock_set_tracking):
        """Test registering baseline with invalid model type."""
        registry = HokusaiModelRegistry()
        mock_model = Mock()

        with pytest.raises(ValueError, match="Invalid model type"):
            registry.register_baseline(mock_model, "invalid_type", {})

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.start_run")
    @patch("mlflow.log_params")
    @patch("mlflow.log_param")
    @patch("mlflow.pyfunc.log_model")
    @patch("mlflow.register_model")
    @patch("mlflow.set_tag")
    def test_register_improved_model(
        self,
        mock_set_tag,
        mock_register_model,
        mock_log_model,
        mock_log_param,
        mock_log_params,
        mock_start_run,
        mock_set_tracking,
    ):
        """Test registering an improved model."""
        # Setup mocks
        mock_run = MagicMock()
        mock_run.info.run_id = "improved_run_123"
        mock_start_run.return_value.__enter__.return_value = mock_run

        mock_model_version = Mock()
        mock_model_version.version = "2"
        mock_register_model.return_value = mock_model_version

        # Create registry and model
        registry = HokusaiModelRegistry()
        mock_model = Mock()

        improvement_data = {
            "baseline_model_id": "hokusai_classification_baseline",
            "baseline_version": "1",
            "contributor_address": "0x123abc",
            "delta_metrics": {"accuracy": 0.03},
        }

        # Register improved model
        result = registry.register_improved_model(mock_model, "classification", improvement_data)

        # Verify result
        assert result["model_id"] == "hokusai_classification_improved"
        assert result["version"] == "2"
        assert result["contributor_address"] == "0x123abc"
        assert result["baseline_model_id"] == "hokusai_classification_baseline"

        # Verify tags
        mock_set_tag.assert_any_call("contributor_address", "0x123abc")
        mock_set_tag.assert_any_call("baseline_model_id", "hokusai_classification_baseline")

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.search_registered_models")
    def test_get_model_lineage(self, mock_search_models, mock_set_tracking):
        """Test getting model lineage."""
        # Mock model versions
        mock_model = Mock()
        mock_model.name = "hokusai_classification_improved"
        mock_model.latest_versions = [
            Mock(version="3", tags={"baseline_version": "2"}),
            Mock(version="2", tags={"baseline_version": "1"}),
            Mock(version="1", tags={}),
        ]
        mock_search_models.return_value = [mock_model]

        registry = HokusaiModelRegistry()
        lineage = registry.get_model_lineage("hokusai_classification_improved")

        assert len(lineage) == 3
        assert lineage[0]["version"] == "1"
        assert lineage[0]["parent_version"] is None
        assert lineage[1]["version"] == "2"
        assert lineage[1]["parent_version"] == "1"
        assert lineage[2]["version"] == "3"
        assert lineage[2]["parent_version"] == "2"

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.search_runs")
    def test_get_contributor_models(self, mock_search_runs, mock_set_tracking):
        """Test getting models by contributor."""
        import pandas as pd

        # Mock search results
        mock_runs = pd.DataFrame(
            [
                {
                    "run_id": "run1",
                    "tags.contributor_address": "0x123abc",
                    "tags.mlflow.parentRunId": None,
                    "params.model_type": "classification",
                    "status": "FINISHED",
                },
                {
                    "run_id": "run2",
                    "tags.contributor_address": "0x123abc",
                    "tags.mlflow.parentRunId": None,
                    "params.model_type": "regression",
                    "status": "FINISHED",
                },
            ]
        )
        mock_search_runs.return_value = mock_runs

        registry = HokusaiModelRegistry()
        models = registry.get_contributor_models("0x123abc")

        assert len(models) == 2
        assert models[0]["contributor_address"] == "0x123abc"
        assert models[1]["contributor_address"] == "0x123abc"

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.tracking.MlflowClient")
    def test_promote_model_to_production(self, mock_client_class, mock_set_tracking):
        """Test promoting model to production."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        registry = HokusaiModelRegistry()
        result = registry.promote_model_to_production("hokusai_classification_improved", "2")

        mock_client.transition_model_version_stage.assert_called_once_with(
            name="hokusai_classification_improved",
            version="2",
            stage="Production",
            archive_existing_versions=True,
        )

        assert result["model_id"] == "hokusai_classification_improved"
        assert result["version"] == "2"
        assert result["stage"] == "Production"

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.tracking.MlflowClient")
    def test_get_production_models(self, mock_client_class, mock_set_tracking):
        """Test getting production models."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock model versions
        mock_versions = [
            Mock(
                name="hokusai_classification_baseline",
                version="1",
                current_stage="Production",
                tags={"model_type": "classification"},
            ),
            Mock(
                name="hokusai_regression_improved",
                version="3",
                current_stage="Production",
                tags={"model_type": "regression"},
            ),
        ]
        mock_client.search_model_versions.return_value = mock_versions

        registry = HokusaiModelRegistry()
        production_models = registry.get_production_models()

        assert len(production_models) == 2
        assert production_models[0]["model_id"] == "hokusai_classification_baseline"
        assert production_models[0]["stage"] == "Production"
        assert production_models[1]["model_id"] == "hokusai_regression_improved"
        assert production_models[1]["stage"] == "Production"
