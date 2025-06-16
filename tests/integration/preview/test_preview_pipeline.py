"""Integration tests for the complete preview pipeline."""

import pytest
import pandas as pd
import numpy as np
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch

# Imports will be added once modules are implemented
# from src.preview.data_loader import PreviewDataLoader
# from src.preview.model_manager import PreviewModelManager
# from src.preview.fine_tuner import PreviewFineTuner
# from src.preview.evaluator import PreviewEvaluator
# from src.preview.output_formatter import PreviewOutputFormatter
# from hokusai_preview import PreviewPipeline


class TestPreviewPipelineIntegration:
    """Integration tests for the preview pipeline."""

    @pytest.fixture
    def sample_contributed_data(self, tmp_path):
        """Create sample contributed data file."""
        np.random.seed(42)
        data = pd.DataFrame({
            'query_id': range(5000),
            'query': [f'query_{i}' for i in range(5000)],
            'label': np.random.randint(0, 2, 5000),
            'features': [np.random.rand(10).tolist() for _ in range(5000)]
        })
        csv_path = tmp_path / "contributed_data.csv"
        data.to_csv(csv_path, index=False)
        return csv_path

    @pytest.fixture
    def large_contributed_data(self, tmp_path):
        """Create large contributed data file for performance testing."""
        np.random.seed(42)
        data = pd.DataFrame({
            'query_id': range(15000),
            'query': [f'query_{i}' for i in range(15000)],
            'label': np.random.randint(0, 2, 15000),
            'features': [np.random.rand(10).tolist() for _ in range(15000)]
        })
        csv_path = tmp_path / "large_contributed_data.csv"
        data.to_csv(csv_path, index=False)
        return csv_path

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_end_to_end_preview(self, sample_contributed_data, tmp_path):
        """Test complete preview pipeline execution."""
        output_file = tmp_path / "preview_output.json"
        
        pipeline = PreviewPipeline()
        result = pipeline.run(
            data_path=sample_contributed_data,
            output_file=output_file,
            output_format='json'
        )
        
        assert result['success'] is True
        assert output_file.exists()
        
        # Verify output structure
        with open(output_file, 'r') as f:
            output_data = json.load(f)
        
        assert output_data['schema_version'] == '1.0'
        assert output_data['preview_metadata']['preview_mode'] is True
        assert 'delta_computation' in output_data
        assert output_data['delta_computation']['delta_one_score'] is not None

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_cli_interface(self, sample_contributed_data, tmp_path):
        """Test CLI interface functionality."""
        import subprocess
        
        output_file = tmp_path / "cli_output.json"
        
        # Run CLI command
        cmd = [
            'python', '-m', 'hokusai_preview',
            '--data-path', str(sample_contributed_data),
            '--output-file', str(output_file),
            '--output-format', 'json'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        assert result.returncode == 0
        assert output_file.exists()
        assert "Preview complete" in result.stdout

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_performance_under_5_minutes(self, large_contributed_data):
        """Test that preview completes in under 5 minutes."""
        pipeline = PreviewPipeline()
        
        start_time = time.time()
        result = pipeline.run(
            data_path=large_contributed_data,
            output_format='json'
        )
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        assert result['success'] is True
        assert execution_time < 300  # 5 minutes = 300 seconds
        print(f"Execution time: {execution_time:.2f} seconds")

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_delta_accuracy_within_20_percent(self, sample_contributed_data):
        """Test that preview delta is within ±20% of full pipeline."""
        # Run preview pipeline
        preview_pipeline = PreviewPipeline()
        preview_result = preview_pipeline.run(
            data_path=sample_contributed_data,
            output_format='json'
        )
        
        preview_delta = preview_result['delta_one_score']
        
        # Simulate full pipeline delta (in real test, would run actual pipeline)
        with patch('src.pipeline.hokusai_pipeline.HokusaiPipeline') as mock_pipeline:
            mock_pipeline.return_value.run.return_value = {
                'delta_one_score': 0.025
            }
            full_pipeline_delta = 0.025
        
        # Check accuracy within ±20%
        relative_error = abs(preview_delta - full_pipeline_delta) / full_pipeline_delta
        assert relative_error <= 0.20

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_pretty_output_format(self, sample_contributed_data, capsys):
        """Test pretty output format."""
        pipeline = PreviewPipeline()
        
        pipeline.run(
            data_path=sample_contributed_data,
            output_format='pretty'
        )
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Verify pretty output contains expected elements
        assert "PREVIEW - NON-BINDING ESTIMATE" in output
        assert "DeltaOne Score:" in output
        assert "Confidence:" in output
        assert "Metrics Comparison:" in output

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_test_mode_with_mock_baseline(self, sample_contributed_data):
        """Test preview in test mode with mock baseline."""
        pipeline = PreviewPipeline(test_mode=True)
        
        result = pipeline.run(
            data_path=sample_contributed_data,
            output_format='json'
        )
        
        assert result['success'] is True
        assert result['baseline_model_type'] == 'mock_baseline'
        assert result['delta_one_score'] is not None

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_custom_baseline_model(self, sample_contributed_data, tmp_path):
        """Test with custom baseline model path."""
        # Create mock baseline model file
        baseline_path = tmp_path / "custom_baseline.pkl"
        baseline_path.write_text("mock model data")
        
        pipeline = PreviewPipeline()
        
        with patch('src.preview.model_manager.PreviewModelManager.load_baseline_model') as mock_load:
            mock_load.return_value = Mock()
            
            result = pipeline.run(
                data_path=sample_contributed_data,
                baseline_model=str(baseline_path),
                output_format='json'
            )
        
        assert result['success'] is True
        mock_load.assert_called_with(baseline_path)

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_sampling_for_large_datasets(self, tmp_path):
        """Test automatic sampling for datasets > 10k samples."""
        # Create dataset with 20k samples
        large_data = pd.DataFrame({
            'query_id': range(20000),
            'query': [f'query_{i}' for i in range(20000)],
            'label': np.random.randint(0, 2, 20000),
            'features': [np.random.rand(10).tolist() for _ in range(20000)]
        })
        large_path = tmp_path / "large_data.csv"
        large_data.to_csv(large_path, index=False)
        
        pipeline = PreviewPipeline()
        result = pipeline.run(
            data_path=large_path,
            output_format='json'
        )
        
        assert result['success'] is True
        assert result['sample_size_used'] == 10000
        assert result['original_data_size'] == 20000

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_error_handling_invalid_data(self, tmp_path):
        """Test error handling for invalid data files."""
        invalid_csv = tmp_path / "invalid.csv"
        invalid_csv.write_text("this is not valid csv data\n!!!")
        
        pipeline = PreviewPipeline()
        
        with pytest.raises(ValueError, match="Failed to load data"):
            pipeline.run(
                data_path=invalid_csv,
                output_format='json'
            )

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_memory_efficiency(self, large_contributed_data):
        """Test memory-efficient processing."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        pipeline = PreviewPipeline()
        result = pipeline.run(
            data_path=large_contributed_data,
            output_format='json'
        )
        
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = peak_memory - initial_memory
        
        assert result['success'] is True
        # Should not use more than 2GB additional memory
        assert memory_increase < 2048

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_reproducibility(self, sample_contributed_data):
        """Test reproducible results with same random seed."""
        pipeline1 = PreviewPipeline(random_seed=42)
        pipeline2 = PreviewPipeline(random_seed=42)
        
        result1 = pipeline1.run(
            data_path=sample_contributed_data,
            output_format='json'
        )
        
        result2 = pipeline2.run(
            data_path=sample_contributed_data,
            output_format='json'
        )
        
        assert result1['delta_one_score'] == result2['delta_one_score']
        assert result1['metrics'] == result2['metrics']

    @pytest.mark.skip(reason="PreviewPipeline not yet implemented")
    def test_verbose_mode(self, sample_contributed_data, capsys):
        """Test verbose mode output."""
        pipeline = PreviewPipeline(verbose=True)
        
        pipeline.run(
            data_path=sample_contributed_data,
            output_format='json'
        )
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Verbose mode should show detailed progress
        assert "Loading data" in output
        assert "Loading baseline model" in output
        assert "Fine-tuning model" in output
        assert "Evaluating models" in output
        assert "Calculating delta" in output