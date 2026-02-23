"""Pytest configuration and fixtures."""

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
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
    # Auth-hook note: all patched MLflow calls here are local test doubles and
    # intentionally avoid live Authorization header/MLFLOW_TRACKING_TOKEN flows.
    with (
        patch("mlflow.set_tracking_uri") as _mock_set_uri,
        patch("mlflow.get_experiment_by_name") as mock_get_exp,
        patch("mlflow.create_experiment") as mock_create_exp,
        patch("mlflow.set_experiment") as _mock_set_exp,
        patch("mlflow.start_run") as mock_start_run,
        patch("mlflow.log_params") as _mock_log_params,
        patch("mlflow.log_metrics") as _mock_log_metrics,
        patch("mlflow.set_tag") as _mock_set_tag,
        patch("mlflow.log_artifact") as _mock_log_artifact,
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


@pytest.fixture
def hek_dataset_hash() -> str:
    """Stable dataset hash used by HEK-focused tests."""
    return "sha256:" + "a" * 64


@pytest.fixture
def make_mlflow_run():
    """Factory for minimal MLflow-like run objects used in HEK tests."""

    def _make(
        run_id: str,
        *,
        metric_name: str = "accuracy",
        metric_value: float = 0.87,
        n_examples: str = "1000",
        dataset_hash: str = "sha256:" + "a" * 64,
        model_id: str = "model-a",
        experiment_id: str = "1",
        start_time_ms: int | None = None,
        extra_metrics: dict[str, float] | None = None,
        tags: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> SimpleNamespace:
        metrics = {metric_name: metric_value}
        if extra_metrics:
            metrics.update(extra_metrics)
        run_tags = {
            "hokusai.primary_metric": metric_name,
            "hokusai.dataset.num_samples": n_examples,
            "hokusai.dataset.hash": dataset_hash,
            "hokusai.dataset.id": "dataset-1",
            "hokusai.model_id": model_id,
            "hokusai.eval_id": "eval-001",
        }
        if tags:
            run_tags.update(tags)
        return SimpleNamespace(
            info=SimpleNamespace(
                run_id=run_id,
                experiment_id=experiment_id,
                start_time=start_time_ms
                if start_time_ms is not None
                else int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
            data=SimpleNamespace(
                metrics=metrics,
                tags=run_tags,
                params=params or {},
            ),
        )

    return _make


@pytest.fixture
def make_fake_deltaone_mlflow_client():
    """Factory for lightweight in-memory client used by DeltaOne tests."""

    class _FakeDeltaOneMlflowClient:
        def __init__(
            self,
            runs: dict[str, SimpleNamespace],
            search_runs_result: list[SimpleNamespace] | None = None,
        ) -> None:
            self._runs = runs
            self._search_runs_result = search_runs_result or []
            self.tags_set: dict[str, dict[str, str]] = {}
            self.search_runs_calls: list[dict[str, object]] = []

        def get_run(self, run_id: str) -> SimpleNamespace:
            return self._runs[run_id]

        def search_runs(
            self,
            experiment_ids: list[str],
            filter_string: str,
            max_results: int,
            order_by: list[str],
        ) -> list[SimpleNamespace]:
            self.search_runs_calls.append(
                {
                    "experiment_ids": experiment_ids,
                    "filter_string": filter_string,
                    "max_results": max_results,
                    "order_by": order_by,
                }
            )
            return self._search_runs_result

        def set_tag(self, run_id: str, key: str, value: str) -> None:
            self.tags_set.setdefault(run_id, {})[key] = value

    return _FakeDeltaOneMlflowClient
