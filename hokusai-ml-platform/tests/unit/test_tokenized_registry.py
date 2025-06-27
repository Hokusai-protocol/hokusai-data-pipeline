"""Unit tests for token-aware MLflow model registry functionality"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import mlflow
from mlflow.exceptions import MlflowException

from hokusai.core.registry import ModelRegistry, RegistryException
from hokusai.core.models import HokusaiModel


class TestTokenizedModelRegistry:
    """Test suite for tokenized model registration"""
    
    @pytest.fixture
    def mock_mlflow_client(self):
        """Mock MLflow client"""
        with patch('hokusai.core.registry.MlflowClient') as mock:
            yield mock
    
    @pytest.fixture
    def mock_model(self):
        """Create a mock HokusaiModel"""
        model = Mock(spec=HokusaiModel)
        model.model_id = "test-model-123"
        model.version = "1.0.0"
        model.get_metrics.return_value = {"accuracy": 0.95}
        return model
    
    @pytest.fixture
    def registry(self, mock_mlflow_client):
        """Create ModelRegistry instance with mocked client"""
        return ModelRegistry("http://test:5000")
    
    def test_register_tokenized_model_success(self, registry, mock_model):
        """Test successful tokenized model registration"""
        # Mock MLflow client methods
        mock_version = Mock()
        mock_version.version = "1"
        registry.client.create_model_version.return_value = mock_version
        registry.client.create_registered_model.return_value = None
        registry.client.set_model_version_tag.return_value = None
        
        # Call register_tokenized_model
        result = registry.register_tokenized_model(
            model_uri="runs:/abc123/model",
            model_name="MSG-AI",
            token_id="msg-ai",
            metric_name="reply_rate",
            baseline_value=0.1342
        )
        
        # Verify model was created
        registry.client.create_model_version.assert_called_once()
        
        # Verify required tags were set
        expected_tags = [
            ("hokusai_token_id", "msg-ai"),
            ("benchmark_metric", "reply_rate"),
            ("benchmark_value", "0.1342")
        ]
        
        for tag_name, tag_value in expected_tags:
            registry.client.set_model_version_tag.assert_any_call(
                name="MSG-AI",
                version="1",
                key=tag_name,
                value=tag_value
            )
        
        assert result["model_name"] == "MSG-AI"
        assert result["version"] == "1"
        assert result["token_id"] == "msg-ai"
    
    def test_register_tokenized_model_invalid_baseline_value(self, registry):
        """Test registration with invalid baseline value"""
        with pytest.raises(ValueError, match="baseline_value must be numeric"):
            registry.register_tokenized_model(
                model_uri="runs:/abc123/model",
                model_name="MSG-AI",
                token_id="msg-ai",
                metric_name="reply_rate",
                baseline_value="invalid"
            )
    
    def test_register_tokenized_model_missing_required_params(self, registry):
        """Test registration with missing required parameters"""
        with pytest.raises(ValueError, match="All parameters are required"):
            registry.register_tokenized_model(
                model_uri="runs:/abc123/model",
                model_name="MSG-AI",
                token_id=None,
                metric_name="reply_rate",
                baseline_value=0.1342
            )
    
    def test_validate_hokusai_tags_success(self, registry):
        """Test successful tag validation"""
        tags = {
            "hokusai_token_id": "msg-ai",
            "benchmark_metric": "reply_rate",
            "benchmark_value": "0.1342"
        }
        
        # Should not raise any exception
        registry.validate_hokusai_tags(tags)
    
    def test_validate_hokusai_tags_missing_required(self, registry):
        """Test validation with missing required tags"""
        tags = {
            "hokusai_token_id": "msg-ai",
            "benchmark_metric": "reply_rate"
            # Missing benchmark_value
        }
        
        with pytest.raises(RegistryException, match="Missing required tag: benchmark_value"):
            registry.validate_hokusai_tags(tags)
    
    def test_validate_hokusai_tags_invalid_value_type(self, registry):
        """Test validation with invalid tag value type"""
        tags = {
            "hokusai_token_id": 123,  # Should be string
            "benchmark_metric": "reply_rate",
            "benchmark_value": "0.1342"
        }
        
        with pytest.raises(RegistryException, match="Tag hokusai_token_id must be a str"):
            registry.validate_hokusai_tags(tags)
    
    def test_validate_hokusai_tags_invalid_benchmark_value(self, registry):
        """Test validation with non-numeric benchmark value"""
        tags = {
            "hokusai_token_id": "msg-ai",
            "benchmark_metric": "reply_rate",
            "benchmark_value": "not-a-number"
        }
        
        with pytest.raises(RegistryException, match="benchmark_value must be convertible to float"):
            registry.validate_hokusai_tags(tags)
    
    def test_get_tokenized_model(self, registry):
        """Test retrieving a tokenized model"""
        # Mock model version with tags
        mock_version = Mock()
        mock_version.name = "MSG-AI"
        mock_version.version = "1"
        mock_version.tags = {
            "hokusai_token_id": "msg-ai",
            "benchmark_metric": "reply_rate",
            "benchmark_value": "0.1342"
        }
        
        registry.client.get_model_version.return_value = mock_version
        
        result = registry.get_tokenized_model("MSG-AI", "1")
        
        assert result["model_name"] == "MSG-AI"
        assert result["version"] == "1"
        assert result["token_id"] == "msg-ai"
        assert result["metric_name"] == "reply_rate"
        assert result["baseline_value"] == 0.1342
    
    def test_list_models_by_token(self, registry):
        """Test listing models by token ID"""
        # Create mock registered models
        mock_rm1 = Mock()
        mock_rm1.name = "MSG-AI"
        mock_rm2 = Mock()
        mock_rm2.name = "OTHER-MODEL"
        
        # Mock version for MSG-AI v1
        mock_v1 = Mock()
        mock_v1.name = "MSG-AI"
        mock_v1.version = "1"
        mock_v1.tags = {
            "hokusai_token_id": "msg-ai",
            "benchmark_metric": "reply_rate", 
            "benchmark_value": "0.15"
        }
        
        # Mock version for MSG-AI v2
        mock_v2 = Mock()
        mock_v2.name = "MSG-AI"
        mock_v2.version = "2"
        mock_v2.tags = {
            "hokusai_token_id": "msg-ai",
            "benchmark_metric": "reply_rate",
            "benchmark_value": "0.16"
        }
        
        # Mock version for OTHER-MODEL
        mock_v3 = Mock()
        mock_v3.name = "OTHER-MODEL"
        mock_v3.version = "1"
        mock_v3.tags = {"hokusai_token_id": "other-token"}
        
        # Set up the mocks
        registry.client.search_registered_models.return_value = [mock_rm1, mock_rm2]
        
        def mock_search_versions(filter_string):
            if "MSG-AI" in filter_string:
                return [mock_v1, mock_v2]
            elif "OTHER-MODEL" in filter_string:
                return [mock_v3]
            return []
        
        registry.client.search_model_versions.side_effect = mock_search_versions
        
        # Mock get_model_version for get_tokenized_model calls
        def mock_get_model_version(name, version):
            if name == "MSG-AI" and version == "1":
                return mock_v1
            elif name == "MSG-AI" and version == "2":
                return mock_v2
            return None
        
        registry.client.get_model_version.side_effect = mock_get_model_version
        
        results = registry.list_models_by_token("msg-ai")
        
        assert len(results) == 2
        assert all(m["token_id"] == "msg-ai" for m in results)
    
    def test_update_model_tags(self, registry):
        """Test updating model tags"""
        registry.client.set_model_version_tag.return_value = None
        
        new_tags = {
            "benchmark_metric": "conversion_rate",
            "benchmark_value": "0.2345"
        }
        
        registry.update_model_tags("MSG-AI", "1", new_tags)
        
        # Verify tags were updated
        for key, value in new_tags.items():
            registry.client.set_model_version_tag.assert_any_call(
                name="MSG-AI",
                version="1",
                key=key,
                value=value
            )
    
    def test_validate_token_id_valid(self, registry):
        """Test token ID validation with valid ID"""
        valid_ids = ["msg-ai", "lead-scorer", "churn-predictor-v2"]
        
        for token_id in valid_ids:
            # Should not raise exception
            registry.validate_token_id(token_id)
    
    def test_validate_token_id_invalid(self, registry):
        """Test token ID validation with invalid ID"""
        invalid_ids = ["MSG AI", "token_with_special@chars", "", "a" * 65]
        
        for token_id in invalid_ids:
            with pytest.raises(ValueError, match="Invalid token ID"):
                registry.validate_token_id(token_id)
    
    def test_register_tokenized_model_with_additional_tags(self, registry):
        """Test registration with additional custom tags"""
        mock_version = Mock()
        mock_version.version = "1"
        registry.client.create_model_version.return_value = mock_version
        registry.client.set_model_version_tag.return_value = None
        
        additional_tags = {
            "dataset": "customer_interactions",
            "environment": "production"
        }
        
        result = registry.register_tokenized_model(
            model_uri="runs:/abc123/model",
            model_name="MSG-AI",
            token_id="msg-ai",
            metric_name="reply_rate",
            baseline_value=0.1342,
            additional_tags=additional_tags
        )
        
        # Verify additional tags were set
        for key, value in additional_tags.items():
            registry.client.set_model_version_tag.assert_any_call(
                name="MSG-AI",
                version="1",
                key=key,
                value=value
            )
    
    def test_mlflow_exception_handling(self, registry):
        """Test handling of MLflow exceptions"""
        registry.client.create_model_version.side_effect = MlflowException("MLflow error")
        
        with pytest.raises(RegistryException, match="Failed to register tokenized model"):
            registry.register_tokenized_model(
                model_uri="runs:/abc123/model",
                model_name="MSG-AI",
                token_id="msg-ai",
                metric_name="reply_rate",
                baseline_value=0.1342
            )