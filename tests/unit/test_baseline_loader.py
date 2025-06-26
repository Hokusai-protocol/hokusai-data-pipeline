"""Unit tests for baseline_loader module."""

import pytest
import json
import pickle
from unittest.mock import Mock, patch

from src.modules.baseline_loader import BaselineModelLoader


class TestBaselineModelLoader:
    """Test cases for BaselineModelLoader class."""
    
    def test_init_default(self):
        """Test BaselineModelLoader initialization with default values."""
        loader = BaselineModelLoader()
        assert loader.mlflow_tracking_uri is None
    
    def test_init_with_tracking_uri(self):
        """Test BaselineModelLoader initialization with tracking URI."""
        test_uri = "http://localhost:5000"
        with patch('mlflow.set_tracking_uri') as mock_set_uri:
            loader = BaselineModelLoader(mlflow_tracking_uri=test_uri)
            assert loader.mlflow_tracking_uri == test_uri
            mock_set_uri.assert_called_once_with(test_uri)
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_parameters')
    @patch('src.modules.baseline_loader.log_step_metrics')
    @patch('mlflow.pyfunc.load_model')
    @patch('mlflow.models.get_model_info')
    @patch('mlflow.set_tag')
    def test_load_from_mlflow_success(self, mock_set_tag, mock_get_model_info, 
                                     mock_load_model, mock_log_metrics, 
                                     mock_log_params, mock_run_context):
        """Test successful model loading from MLflow registry."""
        # Setup mocks
        mock_model = Mock()
        mock_load_model.return_value = mock_model
        mock_model_info = Mock()
        mock_model_info.run_id = "test_run_id"
        mock_model_info.model_uuid = "test_uuid"
        mock_get_model_info.return_value = mock_model_info
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        loader = BaselineModelLoader()
        result = loader.load_from_mlflow("test_model", "1", "test_run", "metaflow_123")
        
        # Assertions
        assert result == mock_model
        mock_load_model.assert_called_once_with("models:/test_model/1")
        mock_log_params.assert_called_once_with({
            "model_name": "test_model",
            "model_version": "1",
            "source": "mlflow_registry"
        })
        mock_log_metrics.assert_called_once()
        assert mock_log_metrics.call_args[0][0]["model_loaded"] == 1
        assert "load_time_seconds" in mock_log_metrics.call_args[0][0]
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_parameters')
    @patch('src.modules.baseline_loader.log_step_metrics')
    @patch('mlflow.pyfunc.load_model')
    def test_load_from_mlflow_latest_version(self, mock_load_model, mock_log_metrics, 
                                           mock_log_params, mock_run_context):
        """Test loading latest version when no version specified."""
        mock_model = Mock()
        mock_load_model.return_value = mock_model
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        loader = BaselineModelLoader()
        result = loader.load_from_mlflow("test_model", None, "test_run", "metaflow_123")
        
        mock_load_model.assert_called_once_with("models:/test_model/latest")
        mock_log_params.assert_called_once_with({
            "model_name": "test_model",
            "model_version": "latest",
            "source": "mlflow_registry"
        })
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_metrics')
    @patch('mlflow.pyfunc.load_model')
    def test_load_from_mlflow_failure(self, mock_load_model, mock_log_metrics, mock_run_context):
        """Test handling of MLflow loading failure."""
        mock_load_model.side_effect = Exception("MLflow error")
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        loader = BaselineModelLoader()
        
        with pytest.raises(Exception, match="MLflow error"):
            loader.load_from_mlflow("test_model", "1", "test_run", "metaflow_123")
        
        mock_log_metrics.assert_called_once_with({"model_loaded": 0})
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_parameters')
    @patch('src.modules.baseline_loader.log_step_metrics')
    @patch('src.modules.baseline_loader.log_model_artifact')
    def test_load_from_path_json_success(self, mock_log_artifact, mock_log_metrics, 
                                        mock_log_params, mock_run_context, temp_dir):
        """Test successful model loading from JSON file."""
        # Create test model file
        model_data = {"type": "test_model", "version": "1.0"}
        model_path = temp_dir / "model.json"
        with open(model_path, "w") as f:
            json.dump(model_data, f)
        
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        loader = BaselineModelLoader()
        result = loader.load_from_path(model_path, "test_run", "metaflow_123")
        
        assert result == model_data
        mock_log_params.assert_called_once()
        params = mock_log_params.call_args[0][0]
        assert params["model_path"] == str(model_path)
        assert params["model_format"] == ".json"
        assert params["source"] == "file_path"
        assert "file_hash" in params
        assert "file_size_bytes" in params
        
        mock_log_metrics.assert_called_once()
        metrics = mock_log_metrics.call_args[0][0]
        assert metrics["model_loaded"] == 1
        assert "load_time_seconds" in metrics
        
        mock_log_artifact.assert_called_once_with(str(model_path), "baseline_model")
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_parameters')
    @patch('src.modules.baseline_loader.log_step_metrics')
    @patch('src.modules.baseline_loader.log_model_artifact')
    def test_load_from_path_pickle_success(self, mock_log_artifact, mock_log_metrics, 
                                          mock_log_params, mock_run_context, temp_dir):
        """Test successful model loading from pickle file."""
        # Create test model file
        model_data = {"type": "test_model", "version": "1.0"}
        model_path = temp_dir / "model.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(model_data, f)
        
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        loader = BaselineModelLoader()
        result = loader.load_from_path(model_path, "test_run", "metaflow_123")
        
        assert result == model_data
        mock_log_params.assert_called_once()
        params = mock_log_params.call_args[0][0]
        assert params["model_format"] == ".pkl"
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_metrics')
    def test_load_from_path_file_not_found(self, mock_log_metrics, mock_run_context, temp_dir):
        """Test handling of missing file."""
        model_path = temp_dir / "nonexistent.json"
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        loader = BaselineModelLoader()
        
        with pytest.raises(FileNotFoundError, match="Model not found at"):
            loader.load_from_path(model_path, "test_run", "metaflow_123")
        
        mock_log_metrics.assert_called_once_with({"model_loaded": 0})
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_parameters')
    @patch('src.modules.baseline_loader.log_step_metrics')
    def test_load_from_path_unsupported_format(self, mock_log_metrics, mock_log_params, 
                                              mock_run_context, temp_dir):
        """Test handling of unsupported file format."""
        # Create file with unsupported extension
        model_path = temp_dir / "model.txt"
        model_path.write_text("some content")
        
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        loader = BaselineModelLoader()
        
        with pytest.raises(ValueError, match="Unsupported model format"):
            loader.load_from_path(model_path, "test_run", "metaflow_123")
        
        mock_log_metrics.assert_called_once_with({"model_loaded": 0})
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_parameters')
    @patch('src.modules.baseline_loader.log_step_metrics')
    def test_load_mock_model(self, mock_log_metrics, mock_log_params, mock_run_context):
        """Test loading mock model."""
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        loader = BaselineModelLoader()
        result = loader.load_mock_model("test_run", "metaflow_123")
        
        # Verify mock model structure
        assert result["type"] == "mock_baseline_model"
        assert result["version"] == "1.0.0"
        assert "metrics" in result
        assert "metadata" in result
        
        # Verify logging calls
        mock_log_params.assert_called_once()
        params = mock_log_params.call_args[0][0]
        assert params["model_type"] == "mock_baseline_model"
        assert params["source"] == "mock"
        
        mock_log_metrics.assert_called_once()
        metrics = mock_log_metrics.call_args[0][0]
        assert metrics["model_loaded"] == 1
        assert "baseline_accuracy" in metrics
        assert "load_time_seconds" in metrics
    
    def test_validate_model_mock(self):
        """Test validation of mock model."""
        mock_model = {
            "type": "mock_baseline_model",
            "version": "1.0.0",
            "metrics": {"accuracy": 0.85}
        }
        
        loader = BaselineModelLoader()
        assert loader.validate_model(mock_model) is True
    
    def test_validate_model_mock_missing_key(self):
        """Test validation failure for mock model missing required key."""
        mock_model = {
            "type": "mock_baseline_model",
            "version": "1.0.0"
            # Missing "metrics" key
        }
        
        loader = BaselineModelLoader()
        
        with pytest.raises(ValueError, match="Mock model missing required key: metrics"):
            loader.validate_model(mock_model)
    
    def test_validate_model_real_with_predict(self):
        """Test validation of real model with predict method."""
        mock_model = Mock()
        mock_model.predict = Mock()
        
        loader = BaselineModelLoader()
        assert loader.validate_model(mock_model) is True
    
    def test_validate_model_real_without_predict(self):
        """Test validation failure for real model without predict method."""
        mock_model = Mock()
        del mock_model.predict  # Remove predict method
        
        loader = BaselineModelLoader()
        
        with pytest.raises(ValueError, match="Model must have a predict method"):
            loader.validate_model(mock_model)


class TestBaselineModelLoaderPerformance:
    """Performance-related tests for BaselineModelLoader."""
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_parameters')
    @patch('src.modules.baseline_loader.log_step_metrics')
    @patch('src.modules.baseline_loader.log_model_artifact')
    def test_load_time_tracking(self, mock_log_artifact, mock_log_metrics, 
                               mock_log_params, mock_run_context, temp_dir):
        """Test that load time is properly tracked."""
        # Create test model file
        model_data = {"type": "test_model"}
        model_path = temp_dir / "model.json"
        with open(model_path, "w") as f:
            json.dump(model_data, f)
        
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        # Mock time.time to control timing
        with patch('time.time', side_effect=[0.0, 1.5]):  # 1.5 second load time
            loader = BaselineModelLoader()
            loader.load_from_path(model_path, "test_run", "metaflow_123")
        
        # Verify load time was logged
        mock_log_metrics.assert_called_once()
        metrics = mock_log_metrics.call_args[0][0]
        assert metrics["load_time_seconds"] == 1.5
    
    @patch('src.modules.baseline_loader.mlflow_run_context')
    @patch('src.modules.baseline_loader.log_step_parameters')
    def test_file_size_logging(self, mock_log_params, mock_run_context, temp_dir):
        """Test that file size is properly logged."""
        # Create test model file with known content
        model_data = {"type": "test_model", "data": "x" * 1000}  # ~1KB
        model_path = temp_dir / "model.json"
        with open(model_path, "w") as f:
            json.dump(model_data, f)
        
        mock_run_context.return_value.__enter__ = Mock(return_value=None)
        mock_run_context.return_value.__exit__ = Mock(return_value=None)
        
        loader = BaselineModelLoader()
        loader.load_from_path(model_path, "test_run", "metaflow_123")
        
        # Verify file size was logged
        mock_log_params.assert_called_once()
        params = mock_log_params.call_args[0][0]
        assert "file_size_bytes" in params
        assert params["file_size_bytes"] > 0


class TestBaselineModelLoaderIntegration:
    """Integration tests for BaselineModelLoader."""
    
    def test_end_to_end_file_loading(self, temp_dir):
        """Test complete file loading workflow without mocking."""
        # Create real model file
        model_data = {
            "type": "integration_test_model",
            "version": "1.0.0",
            "algorithm": "test_algorithm",
            "metrics": {"accuracy": 0.9}
        }
        model_path = temp_dir / "integration_model.json"
        with open(model_path, "w") as f:
            json.dump(model_data, f)
        
        # Test loading with minimal mocking (only MLflow context)
        with patch('src.modules.baseline_loader.mlflow_run_context') as mock_context:
            mock_context.return_value.__enter__ = Mock(return_value=None)
            mock_context.return_value.__exit__ = Mock(return_value=None)
            
            loader = BaselineModelLoader()
            result = loader.load_from_path(model_path, "integration_test", "meta_123")
            
            # Verify model was loaded correctly
            assert result == model_data
            assert result["type"] == "integration_test_model"
    
    def test_validation_workflow(self):
        """Test model validation workflow."""
        loader = BaselineModelLoader()
        
        # Test valid mock model
        mock_model = {
            "type": "mock_test_model",
            "version": "1.0",
            "metrics": {"accuracy": 0.85}
        }
        assert loader.validate_model(mock_model) is True
        
        # Test valid real model
        real_model = Mock()
        real_model.predict = Mock(return_value=[1, 0, 1])
        assert loader.validate_model(real_model) is True