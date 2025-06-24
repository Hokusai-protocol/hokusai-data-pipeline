"""Pytest configuration and shared fixtures"""
import pytest
import asyncio
from unittest.mock import Mock, MagicMock
import tempfile
import shutil
from pathlib import Path
import mlflow
import redis
from typing import Generator, Any

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create temporary directory for test files"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


@pytest.fixture
def mock_mlflow_client():
    """Mock MLflow client for testing"""
    client = MagicMock()
    client.create_registered_model = Mock(return_value=Mock(name="test_model"))
    client.create_model_version = Mock(return_value=Mock(version="1"))
    client.get_latest_versions = Mock(return_value=[])
    client.search_model_versions = Mock(return_value=[])
    client.set_model_version_tag = Mock()
    client.transition_model_version_stage = Mock()
    return client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing"""
    client = MagicMock(spec=redis.Redis)
    client.get = Mock(return_value=None)
    client.set = Mock(return_value=True)
    client.setex = Mock(return_value=True)
    client.delete = Mock(return_value=1)
    client.exists = Mock(return_value=0)
    client.expire = Mock(return_value=True)
    client.pipeline = Mock(return_value=MagicMock())
    return client


@pytest.fixture
def sample_model_metadata():
    """Sample model metadata for testing"""
    return {
        "model_id": "test-model-001",
        "model_type": "classification",
        "version": "1.0.0",
        "author": "test_user",
        "description": "Test model for unit tests",
        "training_dataset": "test_dataset_v1",
        "hyperparameters": {
            "learning_rate": 0.01,
            "n_estimators": 100,
            "max_depth": 5
        },
        "metrics": {
            "accuracy": 0.95,
            "precision": 0.94,
            "recall": 0.93,
            "f1_score": 0.935
        }
    }


@pytest.fixture
def sample_inference_data():
    """Sample data for inference testing"""
    return {
        "features": [
            0.5, 0.3, 0.8, 0.1, 0.9,
            0.2, 0.7, 0.4, 0.6, 0.15
        ],
        "categorical_features": {
            "category_a": "value1",
            "category_b": "value2"
        },
        "metadata": {
            "source": "test",
            "timestamp": "2024-01-01T00:00:00Z"
        }
    }


@pytest.fixture
def mock_model_artifact(temp_dir):
    """Create mock model artifact files"""
    model_dir = temp_dir / "model"
    model_dir.mkdir()
    
    # Create mock model files
    (model_dir / "model.pkl").write_text("mock model content")
    (model_dir / "config.json").write_text('{"version": "1.0.0"}')
    (model_dir / "requirements.txt").write_text("scikit-learn==1.3.0\nnumpy==1.24.0")
    
    return model_dir


@pytest.fixture(autouse=True)
def reset_mlflow_tracking():
    """Reset MLflow tracking URI for each test"""
    mlflow.set_tracking_uri("file:///tmp/mlflow-test")
    yield
    # Clean up after test
    mlflow.tracking.MlflowClient()._tracking_client._registry_uri = None


@pytest.fixture
def mock_ab_test_config():
    """Sample A/B test configuration"""
    return {
        "test_id": "test-001",
        "model_a": "model-v1",
        "model_b": "model-v2",
        "traffic_split": {"model_a": 0.5, "model_b": 0.5},
        "duration_hours": 24,
        "metrics_to_track": ["latency", "accuracy", "error_rate"],
        "success_criteria": {
            "metric": "accuracy",
            "improvement_threshold": 0.02,
            "confidence_level": 0.95
        }
    }


@pytest.fixture
def mock_experiment_data():
    """Sample experiment data for testing"""
    return {
        "experiment_id": "exp-001",
        "experiment_name": "lead_scoring_improvement",
        "baseline_model_id": "model-v1",
        "candidate_models": ["model-v2", "model-v3"],
        "test_dataset": "test_set_v1",
        "metrics": {
            "model-v1": {"accuracy": 0.85, "f1": 0.82},
            "model-v2": {"accuracy": 0.88, "f1": 0.86},
            "model-v3": {"accuracy": 0.87, "f1": 0.85}
        },
        "parameters": {
            "test_size": 0.2,
            "random_seed": 42,
            "stratify": True
        }
    }


# Markers for different test categories
def pytest_configure(config):
    """Configure custom pytest markers"""
    config.addinivalue_line(
        "markers", "unit: Unit tests that don't require external services"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that may require external services"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take more than 1 second to run"
    )
    config.addinivalue_line(
        "markers", "requires_redis: Tests that require Redis connection"
    )
    config.addinivalue_line(
        "markers", "requires_mlflow: Tests that require MLflow server"
    )