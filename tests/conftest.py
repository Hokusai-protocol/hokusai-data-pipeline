"""Pytest configuration and fixtures."""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from src.utils.config import get_test_config


def pytest_collection_modifyitems(items):
    """Apply standard test marks by directory so default runs stay offline-safe."""
    integration_like_files = {
        "/tests/load/",
        "/tests/test_infrastructure_investigation.py",
        "/tests/test_mlflow_auth.py",
        "/tests/test_mlflow_error_handling.py",
        "/tests/test_mlflow_routing_verification.py",
        "/tests/test_model_registration_flow.py",
        "/tests/test_routing.py",
    }

    for item in items:
        path = str(item.fspath)
        if "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/tests/e2e/" in path:
            item.add_marker(pytest.mark.e2e)
        elif "/tests/chaos/" in path:
            item.add_marker(pytest.mark.chaos)
        elif any(pattern in path for pattern in integration_like_files):
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def test_config():
    """Get test configuration."""
    return get_test_config()


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_data():
    """Create sample dataset for testing."""
    np.random.seed(42)
    n_samples = 1000

    data = pd.DataFrame(
        {
            "query_id": [f"q_{i}" for i in range(n_samples)],
            "query_text": [f"sample query {i}" for i in range(n_samples)],
            "feature_1": np.random.randn(n_samples),
            "feature_2": np.random.randn(n_samples),
            "feature_3": np.random.randn(n_samples),
            "label": np.random.randint(0, 2, n_samples),
        }
    )

    return data


@pytest.fixture
def mock_baseline_model():
    """Create mock baseline model."""
    return {
        "type": "mock_baseline_model",
        "version": "1.0.0",
        "metrics": {"accuracy": 0.85, "precision": 0.83, "recall": 0.87, "f1": 0.85, "auroc": 0.91},
        "metadata": {"training_samples": 50000, "features": 3},
    }


@pytest.fixture
def mock_new_model():
    """Create mock new model."""
    return {
        "type": "mock_new_model",
        "version": "2.0.0",
        "metrics": {"accuracy": 0.88, "precision": 0.86, "recall": 0.89, "f1": 0.87, "auroc": 0.93},
        "metadata": {"training_samples": 60000, "features": 3},
    }


@pytest.fixture
def sample_contributed_data(temp_dir):
    """Create sample contributed data file."""
    data = pd.DataFrame(
        {
            "query_id": [f"contrib_q_{i}" for i in range(100)],
            "query_text": [f"contributed query {i}" for i in range(100)],
            "feature_1": np.random.randn(100),
            "feature_2": np.random.randn(100),
            "feature_3": np.random.randn(100),
            "label": np.random.randint(0, 2, 100),
        }
    )

    # Save as CSV
    csv_path = temp_dir / "contributed_data.csv"
    data.to_csv(csv_path, index=False)

    # Save as JSON
    json_path = temp_dir / "contributed_data.json"
    data.to_json(json_path, orient="records")

    # Save as Parquet
    parquet_path = temp_dir / "contributed_data.parquet"
    data.to_parquet(parquet_path)

    return {
        "data": data,
        "csv_path": csv_path,
        "json_path": json_path,
        "parquet_path": parquet_path,
    }


@pytest.fixture
def sample_model_path(temp_dir):
    """Create sample model file."""
    model_data = {"type": "test_model", "version": "1.0.0", "weights": [0.1, 0.2, 0.3]}

    model_path = temp_dir / "model.json"
    with open(model_path, "w") as f:
        json.dump(model_data, f)

    return model_path


@pytest.fixture(autouse=True)
def mock_mlflow_globally():
    """Mock MLflow globally to prevent actual connections in tests."""
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.get_experiment_by_name") as mock_get_exp,
        patch("mlflow.create_experiment") as mock_create_exp,
        patch("mlflow.set_experiment"),
        patch("mlflow.start_run") as mock_start_run,
        patch("mlflow.log_params"),
        patch("mlflow.log_metrics"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.pyfunc.load_model") as mock_load_model,
        patch("mlflow.models.get_model_info") as mock_get_model_info,
    ):
        # Setup default return values
        mock_get_exp.return_value = Mock(experiment_id="test_exp_id")
        mock_create_exp.return_value = "test_exp_id"
        mock_start_run.return_value.__enter__ = Mock(
            return_value=Mock(info=Mock(run_id="test_run_id"))
        )
        mock_start_run.return_value.__exit__ = Mock(return_value=None)
        mock_load_model.return_value = Mock()
        mock_get_model_info.return_value = Mock(run_id="test_run_id", model_uuid="test_uuid")

        yield


@pytest.fixture(autouse=True)
def set_test_env_vars():
    """Set environment variables for testing."""
    test_env = {
        "MLFLOW_TRACKING_URI": "file:///tmp/test_mlruns",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "POSTGRES_URI": "postgresql://test:test@localhost:5432/test",
        "AWS_ACCESS_KEY_ID": "test_access_key",
        "AWS_SECRET_ACCESS_KEY": "test_secret_key",
        "AWS_SESSION_TOKEN": "test_session_token",
        "AWS_DEFAULT_REGION": "us-east-1",
    }

    original_env = {}
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    # Restore original environment
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def mock_aws_credentials(monkeypatch):
    """Mock AWS credentials for tests."""
    # This prevents boto3 from trying to load real credentials
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
