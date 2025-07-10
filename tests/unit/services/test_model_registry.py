"""Unit tests for the HokusaiModelRegistry service."""

from unittest.mock import Mock, patch

import pytest

from src.services.model_registry import HokusaiModelRegistry


class TestHokusaiModelRegistry:
    """Test cases for HokusaiModelRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a registry instance for testing."""
        with patch("mlflow.set_tracking_uri"):
            return HokusaiModelRegistry()

    @pytest.fixture
    def mock_model(self):
        """Create a mock model for testing."""
        model = Mock()
        model.predict = Mock(return_value=[0.8, 0.2])
        return model

    def test_init_default(self):
        """Test HokusaiModelRegistry initialization with default values."""
        with patch("mlflow.set_tracking_uri") as mock_set_uri:
            registry = HokusaiModelRegistry()
            assert registry.tracking_uri == "http://mlflow-server:5000"
            mock_set_uri.assert_called_once_with("http://mlflow-server:5000")

    def test_init_custom_uri(self):
        """Test HokusaiModelRegistry initialization with custom URI."""
        custom_uri = "http://custom-mlflow:8080"
        with patch("mlflow.set_tracking_uri") as mock_set_uri:
            registry = HokusaiModelRegistry(tracking_uri=custom_uri)
            assert registry.tracking_uri == custom_uri
            mock_set_uri.assert_called_once_with(custom_uri)

    @patch("mlflow.register_model")
    @patch("mlflow.pyfunc.log_model")
    @patch("mlflow.start_run")
    def test_register_baseline_success(
        self, mock_start_run, mock_log_model, mock_register_model, registry, mock_model
    ):
        """Test successful baseline model registration."""
        # Setup mocks
        mock_run = Mock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__ = Mock(return_value=mock_run)
        mock_start_run.return_value.__exit__ = Mock(return_value=None)

        mock_model_version = Mock()
        mock_model_version.version = "1"
        mock_model_version.name = "test_model"
        mock_register_model.return_value = mock_model_version

        # Test metadata
        metadata = {
            "dataset": "initial_training",
            "version": "1.0.0",
            "description": "Initial baseline model",
        }

        # Execute
        result = registry.register_baseline(
            model=mock_model, model_type="lead_scoring", metadata=metadata
        )

        # Verify
        assert result["model_id"] == "test_model/1"
        assert result["model_name"] == "test_model"
        assert result["version"] == "1"
        assert result["model_type"] == "lead_scoring"

        # Check MLflow calls
        mock_log_model.assert_called_once()
        log_call_args = mock_log_model.call_args
        assert log_call_args[1]["artifact_path"] == "model"
        assert log_call_args[1]["registered_model_name"] == "hokusai_lead_scoring_baseline"

    @patch("mlflow.tracking.MlflowClient")
    @patch("mlflow.register_model")
    @patch("mlflow.pyfunc.log_model")
    @patch("mlflow.log_metrics")
    @patch("mlflow.log_params")
    @patch("mlflow.start_run")
    def test_register_improved_model_success(
        self,
        mock_start_run,
        mock_log_params,
        mock_log_metrics,
        mock_log_model,
        mock_register_model,
        mock_client_class,
        registry,
        mock_model,
    ):
        """Test successful improved model registration with delta metrics."""
        # Setup mocks
        mock_run = Mock()
        mock_run.info.run_id = "improved_run_id"
        mock_start_run.return_value.__enter__ = Mock(return_value=mock_run)
        mock_start_run.return_value.__exit__ = Mock(return_value=None)

        mock_model_version = Mock()
        mock_model_version.version = "2"
        mock_model_version.name = "test_model_improved"
        mock_register_model.return_value = mock_model_version

        # Setup MLflow client mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Test data
        baseline_id = "baseline_model/1"
        delta_metrics = {
            "accuracy_improvement": 0.05,
            "auroc_improvement": 0.03,
            "f1_improvement": 0.04,
        }
        contributor = "0x742d35Cc6634C0532925a3b844Bc9e7595f62341"

        # Execute
        result = registry.register_improved_model(
            model=mock_model,
            baseline_id=baseline_id,
            delta_metrics=delta_metrics,
            contributor=contributor,
        )

        # Verify
        assert result["model_id"] == "test_model_improved/2"
        assert result["baseline_id"] == baseline_id
        assert result["contributor"] == contributor
        assert result["delta_metrics"] == delta_metrics

        # Check MLflow calls
        mock_log_metrics.assert_called_once_with(delta_metrics)
        mock_log_params.assert_called()

        # Check that the params were logged correctly
        call_args = mock_log_params.call_args[0][0]
        assert call_args["baseline_model_id"] == baseline_id
        assert call_args["contributor_address"] == contributor

    @patch("mlflow.tracking.MlflowClient")
    def test_get_model_lineage_success(self, mock_client_class, registry):
        """Test retrieving complete model lineage."""
        # Create mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Setup mock version data
        mock_versions = [
            Mock(version="1", run_id="run1", creation_timestamp=1000),
            Mock(version="2", run_id="run2", creation_timestamp=2000),
            Mock(version="3", run_id="run3", creation_timestamp=3000),
        ]
        mock_client.search_model_versions.return_value = mock_versions

        # Setup mock run data
        def get_run_side_effect(run_id):
            run_data = {
                "run1": {"params": {"is_baseline": "True"}, "metrics": {"accuracy": 0.85}},
                "run2": {
                    "params": {"contributor_address": "0xABC123", "baseline_model_id": "model/1"},
                    "metrics": {"accuracy": 0.87, "accuracy_improvement": 0.02},
                },
                "run3": {
                    "params": {"contributor_address": "0xDEF456", "baseline_model_id": "model/2"},
                    "metrics": {"accuracy": 0.89, "accuracy_improvement": 0.02},
                },
            }
            mock_run = Mock()
            mock_run.data.params = run_data[run_id]["params"]
            mock_run.data.metrics = run_data[run_id]["metrics"]
            return mock_run

        mock_client.get_run.side_effect = get_run_side_effect

        # Execute
        lineage = registry.get_model_lineage("test_model")

        # Verify
        assert len(lineage) == 3
        assert lineage[0]["version"] == "1"
        assert lineage[0]["is_baseline"] is True
        assert lineage[1]["contributor"] == "0xABC123"
        assert lineage[2]["contributor"] == "0xDEF456"
        assert lineage[2]["cumulative_improvement"]["accuracy"] == 0.04

    def test_register_baseline_missing_model(self, registry):
        """Test baseline registration with missing model."""
        with pytest.raises(ValueError, match="Model cannot be None"):
            registry.register_baseline(model=None, model_type="lead_scoring", metadata={})

    def test_register_baseline_invalid_model_type(self, registry, mock_model):
        """Test baseline registration with invalid model type."""
        with pytest.raises(ValueError, match="Invalid model type"):
            registry.register_baseline(model=mock_model, model_type="invalid_type", metadata={})

    def test_register_improved_invalid_contributor_address(self, registry, mock_model):
        """Test improved model registration with invalid ETH address."""
        with pytest.raises(ValueError, match="Invalid Ethereum address"):
            registry.register_improved_model(
                model=mock_model,
                baseline_id="baseline/1",
                delta_metrics={"accuracy_improvement": 0.02},
                contributor="invalid_address",
            )

    @patch("mlflow.tracking.MlflowClient")
    def test_get_model_lineage_not_found(self, mock_client_class, registry):
        """Test lineage retrieval for non-existent model."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.search_model_versions.return_value = []

        with pytest.raises(ValueError, match="Model .* not found"):
            registry.get_model_lineage("non_existent_model")

    def test_calculate_cumulative_metrics(self, registry):
        """Test cumulative metrics calculation."""
        versions = [
            {"is_baseline": True, "metrics": {"accuracy": 0.85}},
            {"is_baseline": False, "metrics": {"accuracy": 0.87, "accuracy_improvement": 0.02}},
            {"is_baseline": False, "metrics": {"accuracy": 0.89, "accuracy_improvement": 0.02}},
        ]

        result = registry._calculate_cumulative_metrics(versions)

        assert result["accuracy"] == 0.04
        assert result["total_improvements"] == 2

    def test_validate_eth_address(self, registry):
        """Test Ethereum address validation."""
        # Valid addresses
        assert registry._validate_eth_address("0x742d35Cc6634C0532925a3b844Bc9e7595f62341") is True
        assert registry._validate_eth_address("0x0000000000000000000000000000000000000000") is True

        # Invalid addresses
        assert registry._validate_eth_address("0x742d35Cc6634C0532925a3b844Bc9e") is False
        assert registry._validate_eth_address("742d35Cc6634C0532925a3b844Bc9e7595f62341") is False
        assert registry._validate_eth_address("invalid") is False
        assert registry._validate_eth_address("") is False
