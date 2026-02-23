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
        mock_model_version.name = "hokusai_classification_baseline"
        mock_model_version.version = "1"
        mock_register_model.return_value = mock_model_version

        # Create registry and model
        registry = HokusaiModelRegistry()
        mock_model = Mock()

        metadata = {"dataset": "test_dataset", "accuracy": 0.85}

        # Register baseline
        result = registry.register_baseline(mock_model, "classification", metadata)

        # Verify result
        assert result["model_id"] == "hokusai_classification_baseline/1"
        assert result["model_name"] == "hokusai_classification_baseline"
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
    @patch("mlflow.tracking.MlflowClient")
    @patch("mlflow.log_metrics")
    @patch("mlflow.pyfunc.log_model")
    @patch("mlflow.register_model")
    def test_register_improved_model(
        self,
        mock_register_model,
        mock_log_model,
        mock_log_metrics,
        mock_client_class,
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
        mock_model_version.name = "hokusai_classification_improved"
        mock_model_version.version = "1"
        mock_register_model.return_value = mock_model_version

        # Mock MLflow client
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Create registry and model
        registry = HokusaiModelRegistry()
        mock_model = Mock()

        baseline_id = "hokusai_classification_baseline/1"
        delta_metrics = {"accuracy": 0.03}
        contributor_address = "0x1234567890123456789012345678901234567890"

        # Register improved model
        result = registry.register_improved_model(
            mock_model, baseline_id, delta_metrics, contributor_address
        )

        # Verify result
        assert result["model_id"] == "hokusai_classification_improved/1"
        assert result["model_name"] == "hokusai_classification_improved"
        assert result["version"] == "1"
        assert result["contributor"] == contributor_address
        assert result["baseline_id"] == baseline_id

        # Verify tags set through client
        mock_client.set_model_version_tag.assert_any_call(
            "hokusai_classification_improved", "1", "baseline_model_id", baseline_id
        )
        mock_client.set_model_version_tag.assert_any_call(
            "hokusai_classification_improved", "1", "contributor", contributor_address
        )

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.tracking.MlflowClient")
    def test_get_model_lineage(self, mock_client_class, mock_set_tracking):
        """Test getting model lineage."""
        # Mock MLflow client
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock model versions
        mock_v1 = Mock()
        mock_v1.version = "1"
        mock_v1.run_id = "run1"
        mock_v1.creation_timestamp = 1000

        mock_v2 = Mock()
        mock_v2.version = "2"
        mock_v2.run_id = "run2"
        mock_v2.creation_timestamp = 2000

        mock_v3 = Mock()
        mock_v3.version = "3"
        mock_v3.run_id = "run3"
        mock_v3.creation_timestamp = 3000

        mock_client.search_model_versions.return_value = [mock_v3, mock_v1, mock_v2]

        # Mock runs
        mock_run1 = Mock()
        mock_run1.data.params = {"is_baseline": "True"}
        mock_run1.data.metrics = {"accuracy": 0.85}

        mock_run2 = Mock()
        mock_run2.data.params = {
            "contributor_address": "0x123",
            "baseline_model_id": "hokusai_classification_baseline/1",
        }
        mock_run2.data.metrics = {"accuracy": 0.87, "accuracy_improvement": 0.02}

        mock_run3 = Mock()
        mock_run3.data.params = {
            "contributor_address": "0x456",
            "baseline_model_id": "hokusai_classification_improved/2",
        }
        mock_run3.data.metrics = {"accuracy": 0.88, "accuracy_improvement": 0.01}

        mock_client.get_run.side_effect = lambda run_id: {
            "run1": mock_run1,
            "run2": mock_run2,
            "run3": mock_run3,
        }[run_id]

        registry = HokusaiModelRegistry()
        lineage = registry.get_model_lineage("hokusai_classification_improved")

        assert len(lineage) == 3
        assert lineage[0]["version"] == "1"
        assert lineage[0]["is_baseline"] is True
        assert lineage[1]["version"] == "2"
        assert lineage[1]["contributor"] == "0x123"
        assert lineage[1]["baseline_id"] == "hokusai_classification_baseline/1"
        assert lineage[2]["version"] == "3"
        assert lineage[2]["contributor"] == "0x456"
        assert lineage[2]["cumulative_improvement"]["accuracy"] == 0.03

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
                    "tags.mlflow.log-model.history": '[{"artifact_path": "model1"}]',
                    "params.model_type": "classification",
                    "params.baseline_model_id": "baseline1",
                    "params.contributor_address": "0x123abc",
                    "metrics.accuracy": 0.95,
                    "status": "FINISHED",
                    "start_time": pd.Timestamp("2024-01-01 10:00:00"),
                },
                {
                    "run_id": "run2",
                    "tags.contributor_address": "0x123abc",
                    "tags.mlflow.parentRunId": None,
                    "tags.mlflow.log-model.history": '[{"artifact_path": "model2"}]',
                    "params.model_type": "regression",
                    "params.baseline_model_id": "baseline2",
                    "params.contributor_address": "0x123abc",
                    "metrics.rmse": 0.05,
                    "status": "FINISHED",
                    "start_time": pd.Timestamp("2024-01-02 10:00:00"),
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

        mock_client.set_registered_model_alias.assert_called_once_with(
            name="hokusai_classification_improved",
            version="2",
            alias="production",
        )
        mock_client.set_model_version_tag.assert_called_once_with(
            name="hokusai_classification_improved",
            version="2",
            key="lifecycle_stage",
            value="Production",
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

        # Mock registered models
        mock_model1 = Mock()
        mock_model1.name = "hokusai_classification_baseline"
        mock_model1.description = "Baseline classification model"
        mock_model1.tags = {"model_type": "classification"}
        mock_model2 = Mock()
        mock_model2.name = "hokusai_regression_improved"
        mock_model2.description = "Improved regression model"
        mock_model2.tags = {"model_type": "regression"}

        mock_client.search_registered_models.return_value = [mock_model1, mock_model2]
        mock_client.get_model_version_by_alias.side_effect = [
            Mock(version="1"),
            Mock(version="3"),
        ]

        registry = HokusaiModelRegistry()
        production_models = registry.get_production_models()

        assert len(production_models) == 2
        assert production_models[0]["model_name"] == "hokusai_classification_baseline"
        assert production_models[0]["stage"] == "Production"
        assert production_models[1]["model_name"] == "hokusai_regression_improved"
        assert production_models[1]["stage"] == "Production"
