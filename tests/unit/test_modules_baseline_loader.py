"""Unit tests for baseline loader module."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from mlflow.exceptions import MlflowException

from src.modules.baseline_loader import BaselineModelLoader


class TestBaselineModelLoader:
    """Test suite for BaselineModelLoader class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.loader = BaselineModelLoader()

    def test_initialization(self):
        """Test loader initialization."""
        assert hasattr(self.loader, "client")
        assert hasattr(self.loader, "cache")
        assert self.loader.cache == {}

    @patch("src.modules.baseline_loader.MlflowClient")
    def test_client_initialization(self, mock_client_class):
        """Test MLflow client initialization."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        loader = BaselineModelLoader()

        assert loader.client == mock_client
        mock_client_class.assert_called_once()

    @patch.object(BaselineModelLoader, "_get_latest_production_version")
    def test_load_baseline_model_production(self, mock_get_prod):
        """Test loading baseline model in production stage."""
        mock_version = Mock()
        mock_version.version = "3"
        mock_version.run_id = "run_123"
        mock_version.current_stage = "Production"
        mock_get_prod.return_value = mock_version

        with patch("mlflow.pyfunc.load_model") as mock_load:
            mock_model = Mock()
            mock_load.return_value = mock_model

            model, version_info = self.loader.load_baseline_model("test_model")

        assert model == mock_model
        assert version_info["version"] == "3"
        assert version_info["stage"] == "Production"
        assert version_info["run_id"] == "run_123"
        mock_load.assert_called_once_with("models:/test_model/3")

    @patch.object(BaselineModelLoader, "_get_latest_production_version")
    @patch.object(BaselineModelLoader, "_get_previous_version")
    def test_load_baseline_model_fallback(self, mock_get_prev, mock_get_prod):
        """Test loading baseline model with fallback to previous version."""
        mock_get_prod.return_value = None

        mock_version = Mock()
        mock_version.version = "2"
        mock_version.run_id = "run_456"
        mock_version.current_stage = "Archived"
        mock_get_prev.return_value = mock_version

        with patch("mlflow.pyfunc.load_model") as mock_load:
            mock_model = Mock()
            mock_load.return_value = mock_model

            model, version_info = self.loader.load_baseline_model("test_model")

        assert model == mock_model
        assert version_info["version"] == "2"
        assert version_info["stage"] == "Archived"

    def test_load_baseline_model_no_versions(self):
        """Test loading baseline model when no versions exist."""
        with patch.object(self.loader, "_get_latest_production_version", return_value=None):
            with patch.object(self.loader, "_get_previous_version", return_value=None):
                with pytest.raises(ValueError, match="No baseline model found"):
                    self.loader.load_baseline_model("test_model")

    def test_load_baseline_model_with_cache(self):
        """Test loading model from cache."""
        # Pre-populate cache
        cached_model = Mock()
        cached_info = {"version": "1", "stage": "Production"}
        self.loader.cache["test_model"] = (cached_model, cached_info)

        model, version_info = self.loader.load_baseline_model("test_model")

        assert model == cached_model
        assert version_info == cached_info

    def test_get_latest_production_version(self):
        """Test getting latest production version."""
        mock_v1 = Mock()
        mock_v1.current_stage = "Archived"
        mock_v1.version = "1"

        mock_v2 = Mock()
        mock_v2.current_stage = "Production"
        mock_v2.version = "2"
        mock_v2.creation_timestamp = 1000

        mock_v3 = Mock()
        mock_v3.current_stage = "Production"
        mock_v3.version = "3"
        mock_v3.creation_timestamp = 2000

        with patch.object(self.loader.client, "search_model_versions") as mock_search:
            mock_search.return_value = [mock_v1, mock_v2, mock_v3]

            result = self.loader._get_latest_production_version("test_model")

        assert result == mock_v3
        mock_search.assert_called_once_with("name='test_model'")

    def test_get_latest_production_version_none_found(self):
        """Test getting production version when none exist."""
        mock_v1 = Mock()
        mock_v1.current_stage = "Archived"

        mock_v2 = Mock()
        mock_v2.current_stage = "Staging"

        with patch.object(self.loader.client, "search_model_versions") as mock_search:
            mock_search.return_value = [mock_v1, mock_v2]

            result = self.loader._get_latest_production_version("test_model")

        assert result is None

    def test_get_previous_version(self):
        """Test getting previous version."""
        mock_v1 = Mock()
        mock_v1.version = "1"
        mock_v1.creation_timestamp = 1000

        mock_v2 = Mock()
        mock_v2.version = "2"
        mock_v2.creation_timestamp = 2000

        mock_v3 = Mock()
        mock_v3.version = "3"
        mock_v3.creation_timestamp = 3000

        with patch.object(self.loader.client, "search_model_versions") as mock_search:
            mock_search.return_value = [mock_v3, mock_v1, mock_v2]

            result = self.loader._get_previous_version("test_model", current_version="3")

        assert result == mock_v2

    def test_get_previous_version_single_version(self):
        """Test getting previous version when only one exists."""
        mock_v1 = Mock()
        mock_v1.version = "1"

        with patch.object(self.loader.client, "search_model_versions") as mock_search:
            mock_search.return_value = [mock_v1]

            result = self.loader._get_previous_version("test_model")

        assert result is None

    @patch("mlflow.pyfunc.load_model")
    def test_load_specific_version(self, mock_load):
        """Test loading a specific model version."""
        mock_model = Mock()
        mock_load.return_value = mock_model

        model = self.loader.load_specific_version("test_model", "5")

        assert model == mock_model
        mock_load.assert_called_once_with("models:/test_model/5")

    def test_get_model_metadata(self):
        """Test getting model metadata."""
        mock_version = Mock()
        mock_version.version = "2"
        mock_version.current_stage = "Staging"
        mock_version.run_id = "run_789"
        mock_version.tags = {"accuracy": "0.85", "dataset": "golden_v2"}
        mock_version.creation_timestamp = 1234567890000

        with patch.object(self.loader.client, "get_model_version") as mock_get:
            mock_get.return_value = mock_version

            metadata = self.loader.get_model_metadata("test_model", "2")

        assert metadata["version"] == "2"
        assert metadata["stage"] == "Staging"
        assert metadata["run_id"] == "run_789"
        assert metadata["tags"] == {"accuracy": "0.85", "dataset": "golden_v2"}
        assert isinstance(metadata["created_at"], datetime)

    def test_list_available_baselines(self):
        """Test listing available baseline models."""
        mock_v1 = Mock()
        mock_v1.version = "1"
        mock_v1.current_stage = "Archived"
        mock_v1.tags = {"accuracy": "0.80"}

        mock_v2 = Mock()
        mock_v2.version = "2"
        mock_v2.current_stage = "Production"
        mock_v2.tags = {"accuracy": "0.85"}

        with patch.object(self.loader.client, "search_model_versions") as mock_search:
            mock_search.return_value = [mock_v1, mock_v2]

            baselines = self.loader.list_available_baselines("test_model")

        assert len(baselines) == 2
        assert baselines[0]["version"] == "2"  # Production first
        assert baselines[0]["stage"] == "Production"
        assert baselines[1]["version"] == "1"
        assert baselines[1]["stage"] == "Archived"

    def test_clear_cache(self):
        """Test clearing the model cache."""
        # Add items to cache
        self.loader.cache["model1"] = (Mock(), {})
        self.loader.cache["model2"] = (Mock(), {})

        assert len(self.loader.cache) == 2

        self.loader.clear_cache()

        assert len(self.loader.cache) == 0

    def test_mlflow_exception_handling(self):
        """Test handling MLflow exceptions."""
        with patch.object(self.loader.client, "search_model_versions") as mock_search:
            mock_search.side_effect = MlflowException("Model not found")

            with pytest.raises(MlflowException, match="Model not found"):
                self.loader._get_latest_production_version("nonexistent_model")
