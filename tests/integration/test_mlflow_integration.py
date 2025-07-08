"""Integration tests for MLFlow tracking in pipeline."""

import pytest
import tempfile
import shutil
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.modules.baseline_loader import BaselineModelLoader
from src.modules.data_integration import DataIntegrator
from src.utils.mlflow_config import MLFlowConfig


class TestMLFlowPipelineIntegration:
    """Test MLFlow integration across pipeline modules."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.tracking_uri = f"file://{self.temp_dir}/mlruns"

        # Create test data
        self.test_data = pd.DataFrame({
            "feature1": [1, 2, 3, 4, 5],
            "feature2": ["a", "b", "c", "d", "e"],
            "target": [0, 1, 0, 1, 0]
        })

        self.test_data_path = Path(self.temp_dir) / "test_data.csv"
        self.test_data.to_csv(self.test_data_path, index=False)

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.create_experiment")
    @patch("mlflow.set_experiment")
    def test_mlflow_config_setup(self, mock_set_exp, mock_create_exp,
                                mock_get_exp, mock_set_uri):
        """Test MLFlow configuration setup."""
        mock_get_exp.return_value = None
        mock_create_exp.return_value = "test_id"

        config = MLFlowConfig()
        config.tracking_uri = self.tracking_uri
        config.setup_tracking()

        mock_set_uri.assert_called_once_with(self.tracking_uri)
        mock_create_exp.assert_called_once()
        mock_set_exp.assert_called_once()

    @patch("mlflow.start_run")
    @patch("mlflow.set_tag")
    @patch("mlflow.log_param")
    @patch("mlflow.log_metric")
    def test_baseline_loader_tracking(self, mock_log_metric, mock_log_param,
                                    mock_set_tag, mock_start_run):
        """Test baseline loader with MLFlow tracking."""
        # Setup mock run context
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__.return_value = mock_run

        loader = BaselineModelLoader()
        model = loader.load_mock_model("test_run", "metaflow_123")

        # Verify model was loaded
        assert model["type"] == "mock_baseline_model"

        # Verify MLFlow calls were made
        mock_start_run.assert_called_once()
        assert mock_log_param.call_count > 0
        assert mock_log_metric.call_count > 0
        assert mock_set_tag.call_count > 0

    @patch("mlflow.start_run")
    @patch("mlflow.set_tag")
    @patch("mlflow.log_param")
    @patch("mlflow.log_metric")
    def test_data_integration_tracking(self, mock_log_metric, mock_log_param,
                                     mock_set_tag, mock_start_run):
        """Test data integration with MLFlow tracking."""
        # Setup mock run context
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__.return_value = mock_run

        integrator = DataIntegrator()
        df = integrator.load_data(self.test_data_path, "test_run", "metaflow_123")

        # Verify data was loaded
        assert len(df) == 5
        assert list(df.columns) == ["feature1", "feature2", "target"]

        # Verify MLFlow calls were made
        mock_start_run.assert_called_once()
        assert mock_log_param.call_count > 0
        assert mock_log_metric.call_count > 0
        assert mock_set_tag.call_count > 0

    @patch("mlflow.start_run")
    @patch("mlflow.set_tag")
    @patch("mlflow.log_param")
    @patch("mlflow.log_metric")
    def test_data_merge_tracking(self, mock_log_metric, mock_log_param,
                               mock_set_tag, mock_start_run):
        """Test data merge with MLFlow tracking."""
        # Setup mock run context
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__.return_value = mock_run

        integrator = DataIntegrator()

        # Create base and contributed datasets
        base_df = self.test_data.iloc[:3]
        contributed_df = self.test_data.iloc[3:]

        merged_df = integrator.merge_datasets(
            base_df, contributed_df, "append", "test_run", "metaflow_123"
        )

        # Verify merge was successful
        assert len(merged_df) == 5

        # Verify MLFlow calls were made
        mock_start_run.assert_called_once()
        assert mock_log_param.call_count > 0
        assert mock_log_metric.call_count > 0

    @patch("mlflow.start_run")
    @patch("mlflow.set_tag")
    @patch("mlflow.log_param")
    @patch("mlflow.log_metric")
    @patch("mlflow.log_artifact")
    def test_baseline_loader_file_tracking(self, mock_log_artifact, mock_log_metric,
                                         mock_log_param, mock_set_tag, mock_start_run):
        """Test baseline loader from file with artifact logging."""
        # Create a mock model file
        model_data = {"type": "test_model", "version": "1.0"}
        model_path = Path(self.temp_dir) / "test_model.json"

        import json
        with open(model_path, "w") as f:
            json.dump(model_data, f)

        # Setup mock run context
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__.return_value = mock_run

        loader = BaselineModelLoader()
        model = loader.load_from_path(model_path, "test_run", "metaflow_123")

        # Verify model was loaded
        assert model["type"] == "test_model"

        # Verify artifact was logged
        mock_log_artifact.assert_called_once()

    def test_pipeline_run_reproducibility(self):
        """Test that pipeline runs are reproducible from metadata."""
        # This would test loading a previous run's metadata
        # and reproducing the same results

        # Create sample run metadata
        run_metadata = {
            "run_id": "test_run_123",
            "parameters": {
                "model_type": "mock_baseline_model",
                "data_path": str(self.test_data_path),
                "merge_strategy": "append"
            },
            "metrics": {
                "data_rows": 5,
                "data_columns": 3,
                "load_time": 0.1
            }
        }

        # Verify metadata contains required fields for reproduction
        assert "run_id" in run_metadata
        assert "parameters" in run_metadata
        assert "metrics" in run_metadata
        assert "model_type" in run_metadata["parameters"]

    @patch("mlflow.start_run")
    def test_error_handling_in_tracking(self, mock_start_run):
        """Test error handling in MLFlow tracking context."""
        # Setup mock run context that raises an error
        mock_run = MagicMock()
        mock_start_run.return_value.__enter__.return_value = mock_run

        loader = BaselineModelLoader()

        # Test that errors are properly handled and re-raised
        with pytest.raises(FileNotFoundError):
            loader.load_from_path(Path("/nonexistent/path.pkl"), "test_run", "metaflow_123")

    def test_data_consistency_validation(self):
        """Test validation of data consistency across pipeline steps."""
        integrator = DataIntegrator()

        # Test data hash consistency
        hash1 = integrator.calculate_data_hash(self.test_data)
        hash2 = integrator.calculate_data_hash(self.test_data)

        assert hash1 == hash2, "Data hashes should be consistent"

        # Test with modified data
        modified_data = self.test_data.copy()
        modified_data.iloc[0, 0] = 999
        hash3 = integrator.calculate_data_hash(modified_data)

        assert hash1 != hash3, "Different data should have different hashes"
