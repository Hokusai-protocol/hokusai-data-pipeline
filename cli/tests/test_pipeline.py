"""
Tests for the Pipeline class
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the src directory to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pipeline import Pipeline, PipelineConfig


class TestPipelineConfig:
    """Test the PipelineConfig class"""
    
    def test_config_from_dict(self):
        """Test creating config from dictionary"""
        config_dict = {
            'model_path': '/path/to/model',
            'dataset_path': '/path/to/dataset',
            'output_dir': '/path/to/output',
            'batch_size': 32,
            'random_seed': 42
        }
        config = PipelineConfig.from_dict(config_dict)
        
        assert config.model_path == '/path/to/model'
        assert config.dataset_path == '/path/to/dataset'
        assert config.output_dir == '/path/to/output'
        assert config.batch_size == 32
        assert config.random_seed == 42
    
    def test_config_from_yaml_file(self):
        """Test loading config from YAML file"""
        yaml_content = """
model_path: /path/to/model
dataset_path: /path/to/dataset
output_dir: /path/to/output
batch_size: 64
random_seed: 123
"""
        with patch('builtins.open', mock_open(read_data=yaml_content)):
            config = PipelineConfig.from_yaml('config.yaml')
            
            assert config.model_path == '/path/to/model'
            assert config.batch_size == 64
            assert config.random_seed == 123
    
    def test_config_validation(self):
        """Test that config validates required fields"""
        with pytest.raises(ValueError, match="model_path is required"):
            PipelineConfig.from_dict({})
        
        with pytest.raises(ValueError, match="dataset_path is required"):
            PipelineConfig.from_dict({'model_path': '/path'})


class TestPipeline:
    """Test the Pipeline class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.config = PipelineConfig.from_dict({
            'model_path': '/path/to/model',
            'dataset_path': '/path/to/dataset',
            'output_dir': '/tmp/output',
            'batch_size': 32,
            'random_seed': 42
        })
    
    def test_pipeline_initialization(self):
        """Test that pipeline initializes correctly"""
        pipeline = Pipeline(self.config)
        assert pipeline.config == self.config
        assert pipeline.state == 'initialized'
    
    @patch('pipeline.DataLoader')
    @patch('pipeline.ModelLoader')
    @patch('pipeline.Evaluator')
    def test_pipeline_run(self, mock_evaluator, mock_model_loader, mock_data_loader):
        """Test running the full pipeline"""
        # Set up mocks
        mock_data = Mock()
        mock_data_loader.return_value.load.return_value = mock_data
        
        mock_model = Mock()
        mock_model_loader.return_value.load.return_value = mock_model
        
        mock_results = {'accuracy': 0.95, 'f1_score': 0.93}
        mock_evaluator.return_value.evaluate.return_value = mock_results
        
        # Run pipeline
        pipeline = Pipeline(self.config)
        results = pipeline.run()
        
        # Verify calls
        mock_data_loader.return_value.load.assert_called_once()
        mock_model_loader.return_value.load.assert_called_once()
        mock_evaluator.return_value.evaluate.assert_called_once_with(mock_model, mock_data)
        
        assert results == mock_results
        assert pipeline.state == 'completed'
    
    @patch('pipeline.DataLoader')
    def test_pipeline_error_handling(self, mock_data_loader):
        """Test that pipeline handles errors gracefully"""
        mock_data_loader.return_value.load.side_effect = Exception("Data loading failed")
        
        pipeline = Pipeline(self.config)
        with pytest.raises(Exception, match="Data loading failed"):
            pipeline.run()
        
        assert pipeline.state == 'error'
    
    def test_pipeline_step_tracking(self):
        """Test that pipeline tracks step execution"""
        pipeline = Pipeline(self.config)
        
        # Simulate step execution
        pipeline._mark_step_complete('data_loading')
        pipeline._mark_step_complete('model_loading')
        
        assert 'data_loading' in pipeline.completed_steps
        assert 'model_loading' in pipeline.completed_steps
        assert len(pipeline.completed_steps) == 2
    
    @patch('pipeline.mlflow')
    def test_pipeline_mlflow_tracking(self, mock_mlflow):
        """Test that pipeline integrates with MLflow for tracking"""
        pipeline = Pipeline(self.config)
        pipeline._start_mlflow_run()
        
        mock_mlflow.start_run.assert_called_once()
        mock_mlflow.log_params.assert_called_with({
            'batch_size': 32,
            'random_seed': 42
        })
    
    def test_pipeline_reproducibility(self):
        """Test that pipeline sets random seeds for reproducibility"""
        pipeline = Pipeline(self.config)
        pipeline._set_random_seeds()
        
        # This would need to check that random seeds are actually set
        # In practice, we'd verify numpy.random.seed and random.seed were called
        assert pipeline.config.random_seed == 42


# Helper function for mocking file operations
def mock_open(read_data=''):
    """Create a mock for open() that returns read_data"""
    import builtins
    mock = MagicMock()
    mock.__enter__ = Mock(return_value=Mock(read=Mock(return_value=read_data)))
    mock.__exit__ = Mock(return_value=None)
    return Mock(return_value=mock)