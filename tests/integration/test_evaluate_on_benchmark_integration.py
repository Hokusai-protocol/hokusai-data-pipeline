"""Integration tests for the evaluate_on_benchmark pipeline step."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from src.pipeline.hokusai_pipeline import HokusaiPipeline
from src.utils.config import get_test_config


class TestEvaluateOnBenchmarkIntegration:
    """Integration tests for the evaluate_on_benchmark step."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test outputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def sample_contributed_data(self, temp_dir):
        """Create sample contributed data file."""
        data = pd.DataFrame(
            {
                "query_id": [f"contrib_q_{i}" for i in range(50)],
                "query_text": [f"contributed query {i}" for i in range(50)],
                "feature_1": np.random.randn(50),
                "feature_2": np.random.randn(50),
                "feature_3": np.random.randn(50),
                "label": np.random.choice([0, 1], size=50),
            }
        )

        file_path = Path(temp_dir) / "contributed_data.csv"
        data.to_csv(file_path, index=False)
        return str(file_path)

    def test_evaluate_on_benchmark_dry_run(self, temp_dir, sample_contributed_data):
        """Test evaluate_on_benchmark step in dry run mode."""
        # Create pipeline instance
        pipeline = HokusaiPipeline()

        # Set pipeline parameters
        pipeline.baseline_model_path = None
        pipeline.contributed_data_path = sample_contributed_data
        pipeline.output_dir = temp_dir
        pipeline.dry_run = True

        # Run pipeline steps up to evaluation
        pipeline.start()
        pipeline.load_baseline_model()
        pipeline.integrate_contributed_data()
        pipeline.train_new_model()

        # Verify prerequisites
        assert hasattr(pipeline, "baseline_model")
        assert hasattr(pipeline, "new_model")
        assert hasattr(pipeline, "integrated_data")

        # Run evaluate_on_benchmark step
        pipeline.evaluate_on_benchmark()

        # Verify evaluation results
        assert hasattr(pipeline, "evaluation_results")
        eval_results = pipeline.evaluation_results

        # Check structure
        assert "baseline_metrics" in eval_results
        assert "new_metrics" in eval_results
        assert "comparison" in eval_results
        assert "delta_score" in eval_results
        assert "evaluation_report" in eval_results
        assert "benchmark_dataset" in eval_results
        assert "evaluation_timestamp" in eval_results
        assert "evaluation_time_seconds" in eval_results

        # Check metrics
        for metrics in [eval_results["baseline_metrics"], eval_results["new_metrics"]]:
            assert "accuracy" in metrics
            assert "precision" in metrics
            assert "recall" in metrics
            assert "f1" in metrics
            assert "auroc" in metrics

            # Verify metric values are valid
            for value in metrics.values():
                assert 0 <= value <= 1

        # Check comparison structure
        comparison = eval_results["comparison"]
        for metric_name, comp_data in comparison.items():
            assert "baseline" in comp_data
            assert "new" in comp_data
            assert "absolute_delta" in comp_data
            assert "relative_delta" in comp_data
            assert "improved" in comp_data

        # Check benchmark dataset metadata
        benchmark_meta = eval_results["benchmark_dataset"]
        assert benchmark_meta["size"] == 1000
        assert benchmark_meta["type"] == "mock_classification_benchmark"
        assert "features" in benchmark_meta

        # Verify evaluation time is reasonable
        assert eval_results["evaluation_time_seconds"] > 0
        assert eval_results["evaluation_time_seconds"] < 10  # Should be fast for mock data

    @patch("src.utils.mlflow_config.mlflow_run_context")
    @patch("src.utils.mlflow_config.log_step_parameters")
    @patch("src.utils.mlflow_config.log_step_metrics")
    def test_evaluate_on_benchmark_mlflow_integration(
        self,
        mock_log_metrics,
        mock_log_params,
        mock_mlflow_context,
        temp_dir,
        sample_contributed_data,
    ):
        """Test MLflow integration in evaluate_on_benchmark step."""
        # Setup mock context manager
        mock_mlflow_context.return_value.__enter__ = Mock()
        mock_mlflow_context.return_value.__exit__ = Mock()

        # Create pipeline instance
        pipeline = HokusaiPipeline()
        pipeline.baseline_model_path = None
        pipeline.contributed_data_path = sample_contributed_data
        pipeline.output_dir = temp_dir
        pipeline.dry_run = True

        # Run pipeline steps
        pipeline.start()
        pipeline.load_baseline_model()
        pipeline.integrate_contributed_data()
        pipeline.train_new_model()
        pipeline.evaluate_on_benchmark()

        # Verify MLflow methods were called
        mock_mlflow_context.assert_called_once()
        mock_log_params.assert_called_once()
        mock_log_metrics.assert_called_once()

        # Verify logged parameters
        logged_params = mock_log_params.call_args[0][0]
        assert "benchmark_size" in logged_params
        assert "benchmark_type" in logged_params
        assert "feature_count" in logged_params
        assert "baseline_model_type" in logged_params
        assert "new_model_type" in logged_params
        assert "evaluation_metrics" in logged_params

        # Verify logged metrics
        logged_metrics = mock_log_metrics.call_args[0][0]
        assert "evaluation_time_seconds" in logged_metrics
        assert "benchmark_size" in logged_metrics
        assert "delta_score" in logged_metrics

        # Check that baseline and new metrics are logged with prefixes
        for metric in ["accuracy", "precision", "recall", "f1", "auroc"]:
            assert f"baseline_{metric}" in logged_metrics
            assert f"new_{metric}" in logged_metrics
            assert f"delta_{metric}" in logged_metrics

    def test_compare_and_output_delta_integration(self, temp_dir, sample_contributed_data):
        """Test integration between evaluate_on_benchmark and compare_and_output_delta."""
        # Create pipeline instance
        pipeline = HokusaiPipeline()
        pipeline.baseline_model_path = None
        pipeline.contributed_data_path = sample_contributed_data
        pipeline.output_dir = temp_dir
        pipeline.dry_run = True

        # Run pipeline steps
        pipeline.start()
        pipeline.load_baseline_model()
        pipeline.integrate_contributed_data()
        pipeline.train_new_model()
        pipeline.evaluate_on_benchmark()

        # Run compare_and_output_delta step
        pipeline.compare_and_output_delta()

        # Verify delta results
        assert hasattr(pipeline, "delta_results")
        assert hasattr(pipeline, "delta_one")
        assert hasattr(pipeline, "delta_output")

        # Check delta_output structure
        delta_output = pipeline.delta_output
        assert "delta_one_score" in delta_output
        assert "model_comparison" in delta_output
        assert "baseline_model" in delta_output
        assert "new_model" in delta_output
        assert "evaluation_metadata" in delta_output
        assert "summary" in delta_output

        # Verify baseline model info
        baseline_info = delta_output["baseline_model"]
        assert "metrics" in baseline_info
        assert "model_id" in baseline_info
        assert "model_type" in baseline_info

        # Verify new model info
        new_info = delta_output["new_model"]
        assert "metrics" in new_info
        assert "model_id" in new_info
        assert "model_type" in new_info
        assert "training_metadata" in new_info

        # Verify evaluation metadata
        eval_meta = delta_output["evaluation_metadata"]
        assert "benchmark_dataset" in eval_meta
        assert "evaluation_timestamp" in eval_meta
        assert "evaluation_time_seconds" in eval_meta
        assert "metrics_calculated" in eval_meta

        # Verify summary
        summary = delta_output["summary"]
        assert "improved_metrics" in summary
        assert "degraded_metrics" in summary
        assert "overall_improvement" in summary

        # Check consistency between evaluation and delta results
        assert pipeline.delta_one == pipeline.evaluation_results["delta_score"]
        assert pipeline.delta_results == pipeline.evaluation_results["comparison"]

    def test_attestation_output_with_enhanced_evaluation(self, temp_dir, sample_contributed_data):
        """Test that attestation output includes enhanced evaluation data."""
        # Create pipeline instance
        pipeline = HokusaiPipeline()
        pipeline.baseline_model_path = None
        pipeline.contributed_data_path = sample_contributed_data
        pipeline.output_dir = temp_dir
        pipeline.dry_run = True

        # Run complete pipeline
        pipeline.start()
        pipeline.load_baseline_model()
        pipeline.integrate_contributed_data()
        pipeline.train_new_model()
        pipeline.evaluate_on_benchmark()
        pipeline.compare_and_output_delta()
        pipeline.generate_attestation_output()

        # Verify attestation output
        assert hasattr(pipeline, "attestation_output")
        attestation = pipeline.attestation_output

        # Check enhanced evaluation data in attestation
        assert "evaluation_results" in attestation
        eval_results = attestation["evaluation_results"]

        assert "baseline_metrics" in eval_results
        assert "new_metrics" in eval_results
        assert "benchmark_metadata" in eval_results
        assert "evaluation_timestamp" in eval_results
        assert "evaluation_time_seconds" in eval_results

        # Check model comparison and delta output
        assert "model_comparison" in attestation
        assert "delta_output" in attestation
        assert "performance_summary" in attestation

        perf_summary = attestation["performance_summary"]
        assert "improved_metrics" in perf_summary
        assert "degraded_metrics" in perf_summary
        assert "overall_improvement" in perf_summary
        assert "total_metrics_evaluated" in perf_summary

        # Verify that the evaluation time and delta score are properly included
        assert eval_results["evaluation_time_seconds"] > 0
        assert attestation["delta_one_score"] is not None

    def test_deterministic_evaluation_results(self, temp_dir, sample_contributed_data):
        """Test that evaluation results are deterministic with fixed random seed."""

        def run_pipeline():
            pipeline = HokusaiPipeline()
            pipeline.baseline_model_path = None
            pipeline.contributed_data_path = sample_contributed_data
            pipeline.output_dir = temp_dir
            pipeline.dry_run = True

            pipeline.start()
            pipeline.load_baseline_model()
            pipeline.integrate_contributed_data()
            pipeline.train_new_model()
            pipeline.evaluate_on_benchmark()

            return pipeline.evaluation_results

        # Run pipeline twice and compare results
        results1 = run_pipeline()
        results2 = run_pipeline()

        # Compare baseline metrics (should be identical due to fixed seed)
        for metric in results1["baseline_metrics"]:
            assert results1["baseline_metrics"][metric] == pytest.approx(
                results2["baseline_metrics"][metric], rel=1e-6
            )

        # Compare new model metrics (should be identical due to fixed seed)
        for metric in results1["new_metrics"]:
            assert results1["new_metrics"][metric] == pytest.approx(
                results2["new_metrics"][metric], rel=1e-6
            )

        # Compare delta scores
        assert results1["delta_score"] == pytest.approx(results2["delta_score"], rel=1e-6)

    def test_error_handling_no_benchmark_data(self, temp_dir):
        """Test error handling when no benchmark data is available."""
        # Create pipeline with minimal data
        pipeline = HokusaiPipeline()
        pipeline.baseline_model_path = None
        pipeline.contributed_data_path = "/nonexistent/path.csv"
        pipeline.output_dir = temp_dir
        pipeline.dry_run = False  # Not dry run to test real data path

        # Mock the integrated_data to simulate missing label column
        pipeline.config = get_test_config()
        pipeline.integrated_data = pd.DataFrame(
            {
                "feature_1": [1, 2, 3],
                "feature_2": [4, 5, 6],
                # Missing 'label' column
            }
        )

        # Should raise ValueError when no suitable benchmark data
        with pytest.raises(ValueError, match="No suitable benchmark data available"):
            pipeline.evaluate_on_benchmark()


class TestEvaluationPerformance:
    """Performance tests for evaluation functionality."""

    def test_evaluation_performance_large_dataset(self, temp_dir):
        """Test evaluation performance with larger dataset."""
        # Create pipeline with larger mock dataset
        pipeline = HokusaiPipeline()
        pipeline.baseline_model_path = None
        pipeline.contributed_data_path = "mock_path"
        pipeline.output_dir = temp_dir
        pipeline.dry_run = True

        # Run initial steps
        pipeline.start()
        pipeline.load_baseline_model()

        # Override with larger mock data
        large_data = pd.DataFrame(
            {
                "query_id": [f"q_{i}" for i in range(10000)],
                "feature_1": np.random.randn(10000),
                "feature_2": np.random.randn(10000),
                "feature_3": np.random.randn(10000),
                "label": np.random.choice([0, 1], size=10000),
            }
        )

        pipeline.integrated_data = large_data
        pipeline.contributed_data = large_data[:1000]  # Subset as contributed
        pipeline.data_manifest = {"data_hash": "test_hash"}

        # Mock new model
        pipeline.new_model = {
            "type": "mock_model",
            "version": "2.0.0",
            "metrics": {
                "accuracy": 0.87,
                "precision": 0.85,
                "recall": 0.89,
                "f1": 0.87,
                "auroc": 0.93,
            },
        }

        # Run evaluation and measure time
        import time

        start_time = time.time()
        pipeline.evaluate_on_benchmark()
        end_time = time.time()

        evaluation_time = end_time - start_time

        # Verify results
        assert hasattr(pipeline, "evaluation_results")
        assert pipeline.evaluation_results["evaluation_time_seconds"] > 0

        # Performance should be reasonable even with larger dataset
        assert evaluation_time < 5.0  # Should complete within 5 seconds
        assert (
            pipeline.evaluation_results["benchmark_dataset"]["size"] == 1000
        )  # Benchmark size limited
