"""Test fixtures for CLI validation tests."""


import pandas as pd
import pytest
from click.testing import CliRunner


@pytest.fixture
def cli_runner():
    """Provide a CLI runner for testing Click commands."""
    return CliRunner()


@pytest.fixture
def sample_dataframe():
    """Create a sample DataFrame for testing."""
    return pd.DataFrame({
        "query_id": ["q_001", "q_002", "q_003", "q_004"],
        "query_text": ["sample query 1", "sample query 2", "sample query 3", "sample query 4"],
        "feature_1": [0.1, 0.2, 0.3, 0.4],
        "feature_2": [0.5, 0.6, 0.7, 0.8],
        "label": [1, 0, 1, 0]
    })


@pytest.fixture
def dataframe_with_pii():
    """Create a DataFrame containing PII for testing."""
    return pd.DataFrame({
        "query_id": ["q_001", "q_002", "q_003"],
        "user_email": ["user@example.com", "test@domain.org", "person@site.net"],
        "phone_number": ["555-123-4567", "(555) 987-6543", "555.111.2222"],
        "ssn": ["123-45-6789", "987-65-4321", "555-44-3333"],
        "feature_1": [0.1, 0.2, 0.3]
    })


@pytest.fixture
def dataframe_with_missing():
    """Create a DataFrame with missing values for testing."""
    return pd.DataFrame({
        "query_id": ["q_001", "q_002", None, "q_004"],
        "feature_1": [0.1, None, 0.3, 0.4],
        "feature_2": [0.5, 0.6, 0.7, None],
        "label": [1, 0, None, 0]
    })


@pytest.fixture
def dataframe_with_outliers():
    """Create a DataFrame with outliers for testing."""
    return pd.DataFrame({
        "query_id": ["q_001", "q_002", "q_003", "q_004", "q_005"],
        "feature_1": [0.1, 0.2, 0.3, 10.0, 0.4],  # 10.0 is an outlier
        "feature_2": [0.5, 0.6, 0.7, 0.8, -5.0],  # -5.0 is an outlier
        "label": [1, 0, 1, 0, 1]
    })


@pytest.fixture
def large_dataframe():
    """Create a large DataFrame for performance testing."""
    n_rows = 10000
    return pd.DataFrame({
        "query_id": [f"q_{i:06d}" for i in range(n_rows)],
        "feature_1": [i * 0.1 for i in range(n_rows)],
        "feature_2": [i * 0.2 for i in range(n_rows)],
        "label": [i % 2 for i in range(n_rows)]
    })


@pytest.fixture
def sample_csv_file(sample_dataframe, tmp_path: str):
    """Create a temporary CSV file for testing."""
    csv_file = tmp_path / "sample.csv"
    sample_dataframe.to_csv(csv_file, index=False)
    return str(csv_file)


@pytest.fixture
def sample_json_file(sample_dataframe, tmp_path: str):
    """Create a temporary JSON file for testing."""
    json_file = tmp_path / "sample.json"
    sample_dataframe.to_json(json_file, orient="records")
    return str(json_file)


@pytest.fixture
def sample_parquet_file(sample_dataframe, tmp_path: str):
    """Create a temporary Parquet file for testing."""
    parquet_file = tmp_path / "sample.parquet"
    sample_dataframe.to_parquet(parquet_file, index=False)
    return str(parquet_file)


@pytest.fixture
def corrupted_csv_file(tmp_path: str):
    """Create a corrupted CSV file for error testing."""
    csv_file = tmp_path / "corrupted.csv"
    with open(csv_file, "w") as f:
        f.write("invalid,csv,content\n")
        f.write("missing,quotes\n")
        f.write("incomplete")
    return str(csv_file)


@pytest.fixture
def sample_schema():
    """Create a sample schema for validation testing."""
    return {
        "required_columns": ["query_id", "query_text", "feature_1", "label"],
        "column_types": {
            "query_id": "object",
            "query_text": "object",
            "feature_1": "float64",
            "label": "int64"
        },
        "value_ranges": {
            "feature_1": {"min": 0.0, "max": 1.0},
            "label": {"values": [0, 1]}
        }
    }


@pytest.fixture
def sample_manifest():
    """Create a sample manifest for testing."""
    return {
        "schema_version": "1.0",
        "file_metadata": {
            "path": "/path/to/file.csv",
            "format": "csv",
            "size": 1024,
            "rows": 100,
            "columns": 5,
            "encoding": "utf-8"
        },
        "validation_results": {
            "schema_valid": True,
            "pii_found": False,
            "quality_score": 0.95,
            "missing_values": {"total": 0, "by_column": {}},
            "outliers": []
        },
        "data_hash": "abcdef123456789",
        "timestamp": "2023-12-07T10:00:00Z",
        "contributor_metadata": {
            "tool_version": "0.1.0"
        }
    }


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    return {
        "schema": {
            "required_columns": ["query_id", "query_text"],
            "column_types": {
                "query_id": "object",
                "query_text": "object"
            }
        },
        "pii_detection": {
            "enabled": True,
            "patterns": {
                "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
            }
        },
        "quality_checks": {
            "max_missing_percentage": 0.1,
            "outlier_detection": True
        }
    }