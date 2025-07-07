"""
Integration tests for the model registration feature
"""
import pytest
import tempfile
import json
import os
import sys
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from cli.model import model
from database import DatabaseConfig, DatabaseConnection, TokenOperations, ModelStatus
from database.models import TokenModel
from validation import MetricValidator, BaselineComparator
from events import EventPublisher, EventType
from click.testing import CliRunner


class TestModelRegistrationIntegration:
    """Integration tests for model registration workflow"""
    
    @pytest.fixture
    def runner(self):
        """Create a CLI test runner"""
        return CliRunner()
    
    @pytest.fixture
    def temp_model_file(self):
        """Create a temporary model file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pkl', delete=False) as f:
            f.write('mock model data')
            temp_path = f.name
        yield temp_path
        os.unlink(temp_path)
    
    @pytest.fixture
    def db_config_file(self):
        """Create a temporary database config file"""
        config = {
            "host": "localhost",
            "port": 5432,
            "database": "hokusai_test",
            "username": "test_user",
            "password": "test_pass",
            "db_type": "postgresql"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            temp_path = f.name
        yield temp_path
        os.unlink(temp_path)
    
    def test_database_config_loading(self, db_config_file):
        """Test loading database configuration from file"""
        config = DatabaseConfig.from_file(db_config_file)
        
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "hokusai_test"
        assert config.username == "test_user"
        assert config.db_type == "postgresql"
    
    def test_database_config_from_env(self):
        """Test loading database configuration from environment"""
        with patch.dict(os.environ, {
            'HOKUSAI_DB_HOST': 'env-host',
            'HOKUSAI_DB_PORT': '3306',
            'HOKUSAI_DB_NAME': 'env-db',
            'HOKUSAI_DB_USER': 'env-user',
            'HOKUSAI_DB_PASSWORD': 'env-pass',
            'HOKUSAI_DB_TYPE': 'mysql'
        }):
            config = DatabaseConfig.from_env()
            
            assert config.host == "env-host"
            assert config.port == 3306
            assert config.database == "env-db"
            assert config.username == "env-user"
            assert config.password == "env-pass"
            assert config.db_type == "mysql"
    
    def test_token_model_operations(self):
        """Test TokenModel class operations"""
        token = TokenModel(
            token_id="XRAY",
            model_status=ModelStatus.DRAFT,
            metric_name="auroc",
            baseline_value=0.82
        )
        
        assert token.is_draft() is True
        assert token.can_register() is True
        
        # Test serialization
        token_dict = token.to_dict()
        assert token_dict["token_id"] == "XRAY"
        assert token_dict["model_status"] == "draft"
        
        # Test deserialization
        token2 = TokenModel.from_dict(token_dict)
        assert token2.token_id == "XRAY"
        assert token2.model_status == ModelStatus.DRAFT
    
    def test_metric_validation_integration(self):
        """Test metric validation with baseline comparison"""
        validator = MetricValidator()
        comparator = BaselineComparator()
        
        # Validate metric
        assert validator.validate_metric_name("auroc") is True
        assert validator.validate_baseline("auroc", 0.82) is True
        
        # Compare performance
        result = comparator.validate_improvement(
            current_value=0.85,
            baseline_value=0.82,
            metric_name="auroc"
        )
        
        assert result["meets_baseline"] is True
        assert result["improvement"] == pytest.approx(0.03)
        assert result["comparison"] == "improved"
    
    def test_event_publishing_integration(self):
        """Test event publishing workflow"""
        publisher = EventPublisher()
        
        # Track published events
        published_events = []
        
        class TestHandler:
            def can_handle(self, event_type):
                return True
            
            def handle(self, event):
                published_events.append(event.to_dict())
                return True
        
        publisher.register_handler(TestHandler())
        
        # Publish token ready event
        success = publisher.publish_token_ready("XRAY", "run-123", {
            "metric": "auroc",
            "value": 0.85
        })
        
        assert success is True
        assert len(published_events) == 1
        assert published_events[0]["event_type"] == "token_ready_for_deploy"
        assert published_events[0]["payload"]["token_id"] == "XRAY"
    
    @patch('cli.model.mlflow')
    @patch('cli.model.DatabaseConnection')
    def test_end_to_end_registration_workflow(self, mock_db_conn, mock_mlflow, 
                                            runner, temp_model_file):
        """Test complete registration workflow"""
        # Mock MLflow
        mock_run = Mock()
        mock_run.info.run_id = "test-run-123"
        mock_mlflow.start_run.return_value.__enter__.return_value = mock_run
        
        # Mock database
        mock_db = Mock()
        mock_db_conn.return_value.session.return_value.__enter__.return_value = mock_db
        
        mock_token_ops = Mock()
        mock_token_ops.validate_token_status.return_value = True
        mock_token_ops.save_mlflow_run_id.return_value = True
        
        with patch('cli.model.TokenOperations', return_value=mock_token_ops):
            # Run registration command
            result = runner.invoke(model, [
                'register',
                '--token-id', 'XRAY',
                '--model-path', temp_model_file,
                '--metric', 'auroc',
                '--baseline', '0.82'
            ])
            
            # Verify success
            assert result.exit_code == 0
            assert "Model registration complete" in result.output
            
            # Verify MLflow was called
            mock_mlflow.log_artifact.assert_called_with(temp_model_file)
            mock_mlflow.log_param.assert_any_call("token_id", "XRAY")
            mock_mlflow.log_param.assert_any_call("metric_name", "auroc")
            
            # Verify database operations
            mock_token_ops.validate_token_status.assert_called_with("XRAY")
            mock_token_ops.save_mlflow_run_id.assert_called()
    
    def test_error_scenarios_integration(self, runner, temp_model_file):
        """Test various error scenarios"""
        # Test with invalid metric
        result = runner.invoke(model, [
            'register',
            '--token-id', 'XRAY',
            '--model-path', temp_model_file,
            '--metric', 'invalid_metric',
            '--baseline', '0.82'
        ])
        
        assert result.exit_code != 0
        assert "Unsupported metric" in result.output