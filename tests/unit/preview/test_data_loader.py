"""Unit tests for preview data loader module."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock

from src.preview.data_loader import PreviewDataLoader


class TestPreviewDataLoader:
    """Test cases for PreviewDataLoader."""

    @pytest.fixture
    def sample_csv_data(self, tmp_path):
        """Create sample CSV data for testing."""
        data = pd.DataFrame({
            'query_id': range(100),
            'query': [f'query_{i}' for i in range(100)],
            'label': np.random.randint(0, 2, 100),
            'features': [f'feature_{i}' for i in range(100)]
        })
        csv_path = tmp_path / "sample_data.csv"
        data.to_csv(csv_path, index=False)
        return csv_path, data

    @pytest.fixture
    def sample_json_data(self, tmp_path):
        """Create sample JSON data for testing."""
        data = [
            {'query_id': i, 'query': f'query_{i}', 'label': i % 2, 'features': f'feature_{i}'}
            for i in range(100)
        ]
        json_path = tmp_path / "sample_data.json"
        with open(json_path, 'w') as f:
            json.dump(data, f)
        return json_path, pd.DataFrame(data)

    @pytest.fixture
    def sample_parquet_data(self, tmp_path):
        """Create sample Parquet data for testing."""
        data = pd.DataFrame({
            'query_id': range(100),
            'query': [f'query_{i}' for i in range(100)],
            'label': np.random.randint(0, 2, 100),
            'features': [f'feature_{i}' for i in range(100)]
        })
        parquet_path = tmp_path / "sample_data.parquet"
        data.to_parquet(parquet_path, index=False)
        return parquet_path, data

    @pytest.fixture
    def large_dataset(self, tmp_path):
        """Create large dataset for sampling tests."""
        data = pd.DataFrame({
            'query_id': range(20000),
            'query': [f'query_{i}' for i in range(20000)],
            'label': np.random.randint(0, 2, 20000),
            'features': [f'feature_{i}' for i in range(20000)]
        })
        csv_path = tmp_path / "large_data.csv"
        data.to_csv(csv_path, index=False)
        return csv_path, data

    def test_load_csv_data(self, sample_csv_data):
        """Test loading CSV data."""
        csv_path, expected_data = sample_csv_data
        loader = PreviewDataLoader()
        
        loaded_data = loader.load_data(csv_path)
        
        assert len(loaded_data) == len(expected_data)
        assert list(loaded_data.columns) == list(expected_data.columns)
        assert loaded_data['query_id'].tolist() == expected_data['query_id'].tolist()

    def test_load_json_data(self, sample_json_data):
        """Test loading JSON data."""
        json_path, expected_data = sample_json_data
        loader = PreviewDataLoader()
        
        loaded_data = loader.load_data(json_path)
        
        assert len(loaded_data) == len(expected_data)
        assert list(loaded_data.columns) == list(expected_data.columns)

    def test_load_parquet_data(self, sample_parquet_data):
        """Test loading Parquet data."""
        parquet_path, expected_data = sample_parquet_data
        loader = PreviewDataLoader()
        
        loaded_data = loader.load_data(parquet_path)
        
        assert len(loaded_data) == len(expected_data)
        assert list(loaded_data.columns) == list(expected_data.columns)

    def test_auto_detect_format(self):
        """Test automatic file format detection."""
        loader = PreviewDataLoader()
        
        assert loader._detect_format("data.csv") == "csv"
        assert loader._detect_format("data.json") == "json"
        assert loader._detect_format("data.parquet") == "parquet"
        assert loader._detect_format("data.CSV") == "csv"  # Case insensitive
        
        with pytest.raises(ValueError, match="Unsupported file format"):
            loader._detect_format("data.txt")

    def test_validate_schema(self, sample_csv_data):
        """Test data schema validation."""
        csv_path, data = sample_csv_data
        loader = PreviewDataLoader()
        loaded_data = loader.load_data(csv_path)
        
        # Should pass with correct schema
        loader.validate_schema(loaded_data)
        
        # Should fail with missing columns
        incomplete_data = loaded_data.drop(columns=['label'])
        with pytest.raises(ValueError, match="Missing required columns"):
            loader.validate_schema(incomplete_data)

    def test_stratified_sampling(self, large_dataset):
        """Test stratified sampling for large datasets."""
        csv_path, data = large_dataset
        loader = PreviewDataLoader(max_samples=10000)
        
        sampled_data = loader.load_data(csv_path, sample=True)
        
        assert len(sampled_data) == 10000
        # Check that label distribution is preserved
        original_ratio = data['label'].value_counts(normalize=True)
        sampled_ratio = sampled_data['label'].value_counts(normalize=True)
        
        for label in original_ratio.index:
            assert abs(original_ratio[label] - sampled_ratio[label]) < 0.05

    def test_progress_indicator(self, sample_csv_data, capsys):
        """Test progress indicator during loading."""
        csv_path, _ = sample_csv_data
        loader = PreviewDataLoader(show_progress=True)
        
        loader.load_data(csv_path)
        
        captured = capsys.readouterr()
        assert "Loading data" in captured.out
        assert "Complete" in captured.out

    def test_empty_file_handling(self, tmp_path):
        """Test handling of empty files."""
        empty_csv = tmp_path / "empty.csv"
        empty_csv.write_text("query_id,query,label,features\n")
        
        loader = PreviewDataLoader()
        with pytest.raises(ValueError, match="Empty dataset"):
            loader.load_data(empty_csv)

    def test_malformed_file_handling(self, tmp_path):
        """Test handling of malformed files."""
        malformed_csv = tmp_path / "malformed.csv"
        malformed_csv.write_text("this,is,not,valid,csv\n1,2,3,4,5,6,7,8")
        
        loader = PreviewDataLoader()
        with pytest.raises(ValueError, match="Failed to load data"):
            loader.load_data(malformed_csv)

    def test_file_not_found(self):
        """Test handling of non-existent files."""
        loader = PreviewDataLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_data(Path("non_existent_file.csv"))

    def test_memory_efficient_loading(self, large_dataset):
        """Test memory-efficient loading for large files."""
        csv_path, _ = large_dataset
        loader = PreviewDataLoader(chunk_size=1000)
        
        # Should load data in chunks without loading entire file into memory
        data = loader.load_data(csv_path)
        assert len(data) > 0