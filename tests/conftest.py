"""Pytest configuration and fixtures."""

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.utils.config import get_test_config


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
