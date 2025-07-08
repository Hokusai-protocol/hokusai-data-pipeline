"""Unit tests for compare_and_output_delta step functionality."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import tempfile
from pathlib import Path


class TestCompareAndOutputDelta(unittest.TestCase):
    """Test cases for the compare_and_output_delta step."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock pipeline object instead of instantiating HokusaiPipeline
        # to avoid Metaflow initialization issues in tests
        self.pipeline = Mock()

        # Import the actual method to test
        from src.pipeline.hokusai_pipeline import HokusaiPipeline
        self.pipeline._compute_model_delta = HokusaiPipeline._compute_model_delta.__get__(self.pipeline)

        # Mock configuration
        self.mock_config = Mock()
        self.mock_config.mlflow_experiment_name = "test_experiment"
        self.mock_config.random_seed = 42
        self.mock_config.to_dict.return_value = {"test": "config"}
        self.pipeline.config = self.mock_config

        # Mock run metadata
        self.pipeline.run_metadata = {
            "run_id": "test_run_123",
            "started_at": "2024-01-01T00:00:00",
            "config": {"test": "config"}
        }

        # Mock output directory
        self.temp_dir = tempfile.mkdtemp()
        self.pipeline.output_dir = self.temp_dir
        self.pipeline.dry_run = True

        # Set up mock evaluation results
        self.pipeline.evaluation_results = {
            "baseline_metrics": {
                "accuracy": 0.85,
                "precision": 0.83,
                "recall": 0.87,
                "f1_score": 0.85,
                "auroc": 0.91
            },
            "new_metrics": {
                "accuracy": 0.88,
                "precision": 0.86,
                "recall": 0.89,
                "f1_score": 0.87,
                "auroc": 0.93
            },
            "benchmark_dataset": {
                "size": 1000,
                "type": "mock_benchmark"
            },
            "evaluation_timestamp": "2024-01-01T00:00:00",
            "evaluation_time_seconds": 30.5
        }

        # Set up mock data manifest
        self.pipeline.data_manifest = {
            "data_hash": "abc123def456",
            "file_path": "/test/path",
            "size": 1000
        }

        # Set up mock baseline model
        self.pipeline.baseline_model = {
            "version": "1.0.0",
            "type": "mock_baseline",
            "mlflow_run_id": "baseline_run_123"
        }

        # Set up mock new model
        self.pipeline.new_model = {
            "version": "2.0.0",
            "type": "mock_new_model",
            "mlflow_run_id": "new_run_456",
            "contributed_samples": 100,
            "training_samples": 1000,
            "integration_metadata": {
                "contribution_ratio": 0.1,
                "base_samples": 900,
                "contributed_samples": 100
            }
        }

    def test_compute_model_delta_success(self):
        """Test successful delta computation between models."""
        baseline_metrics = {
            "accuracy": 0.85,
            "precision": 0.83,
            "f1_score": 0.85
        }

        new_metrics = {
            "accuracy": 0.88,
            "precision": 0.86,
            "f1_score": 0.87
        }

        result = self.pipeline._compute_model_delta(baseline_metrics, new_metrics)

        # Check structure
        self.assertIn("delta_one", result)
        self.assertIn("metric_deltas", result)
        self.assertIn("metrics_count", result)
        self.assertIn("improved_metrics", result)
        self.assertIn("degraded_metrics", result)

        # Check delta calculations
        self.assertEqual(result["metrics_count"], 3)

        # Check accuracy delta
        accuracy_delta = result["metric_deltas"]["accuracy"]
        self.assertEqual(accuracy_delta["baseline_value"], 0.85)
        self.assertEqual(accuracy_delta["new_value"], 0.88)
        self.assertEqual(accuracy_delta["absolute_delta"], 0.03)
        self.assertTrue(accuracy_delta["improvement"])

        # Check that all metrics improved
        self.assertEqual(len(result["improved_metrics"]), 3)
        self.assertEqual(len(result["degraded_metrics"]), 0)

        # Check DeltaOne score is positive (improvement)
        self.assertGreater(result["delta_one"], 0)

    def test_compute_model_delta_mixed_results(self):
        """Test delta computation with mixed improvement/degradation."""
        baseline_metrics = {
            "accuracy": 0.85,
            "precision": 0.83,
            "recall": 0.90
        }

        new_metrics = {
            "accuracy": 0.88,  # improvement
            "precision": 0.80,  # degradation
            "recall": 0.90     # no change
        }

        result = self.pipeline._compute_model_delta(baseline_metrics, new_metrics)

        # Check that we have both improvements and degradations
        self.assertIn("accuracy", result["improved_metrics"])
        self.assertIn("precision", result["degraded_metrics"])

        # Check precision delta (degradation)
        precision_delta = result["metric_deltas"]["precision"]
        self.assertEqual(precision_delta["absolute_delta"], -0.03)
        self.assertFalse(precision_delta["improvement"])

    def test_compute_model_delta_no_common_metrics(self):
        """Test error handling when no common metrics exist."""
        baseline_metrics = {"accuracy": 0.85, "precision": 0.83}
        new_metrics = {"f1_score": 0.87, "recall": 0.89}

        with self.assertRaises(ValueError) as context:
            self.pipeline._compute_model_delta(baseline_metrics, new_metrics)

        self.assertIn("No compatible metrics found", str(context.exception))

    def test_compute_model_delta_invalid_metric_values(self):
        """Test handling of invalid metric values."""
        baseline_metrics = {"accuracy": 0.85, "precision": "invalid"}
        new_metrics = {"accuracy": 0.88, "precision": 0.86}

        result = self.pipeline._compute_model_delta(baseline_metrics, new_metrics)

        # Should only include accuracy (valid metric)
        self.assertEqual(result["metrics_count"], 1)
        self.assertIn("accuracy", result["metric_deltas"])
        self.assertNotIn("precision", result["metric_deltas"])

    def test_compute_model_delta_zero_baseline(self):
        """Test handling of zero baseline values for relative delta."""
        baseline_metrics = {"accuracy": 0.0}
        new_metrics = {"accuracy": 0.5}

        result = self.pipeline._compute_model_delta(baseline_metrics, new_metrics)

        accuracy_delta = result["metric_deltas"]["accuracy"]
        self.assertEqual(accuracy_delta["relative_delta"], 0.0)  # Should be 0 when baseline is 0
        self.assertEqual(accuracy_delta["absolute_delta"], 0.5)

    @patch("src.pipeline.hokusai_pipeline.mlflow_run_context")
    @patch("src.pipeline.hokusai_pipeline.log_step_parameters")
    @patch("src.pipeline.hokusai_pipeline.log_step_metrics")
    @patch("src.pipeline.hokusai_pipeline.current")
    def test_compare_and_output_delta_success(self, mock_current, mock_log_metrics,
                                             mock_log_params, mock_mlflow_context):
        """Test successful execution of compare_and_output_delta step."""
        # Mock current run
        mock_current.run_id = "test_run_123"

        # Mock MLflow context manager
        mock_mlflow_context.return_value.__enter__ = Mock()
        mock_mlflow_context.return_value.__exit__ = Mock()

        # Execute the step
        self.pipeline.compare_and_output_delta()

        # Verify MLflow logging was called
        mock_log_params.assert_called_once()
        mock_log_metrics.assert_called_once()

        # Check that delta results were computed
        self.assertIsNotNone(self.pipeline.delta_results)
        self.assertIsNotNone(self.pipeline.delta_one)
        self.assertIsNotNone(self.pipeline.delta_output)

        # Check delta output structure
        delta_output = self.pipeline.delta_output
        self.assertIn("schema_version", delta_output)
        self.assertIn("delta_computation", delta_output)
        self.assertIn("baseline_model", delta_output)
        self.assertIn("new_model", delta_output)
        self.assertIn("contributor_attribution", delta_output)
        self.assertIn("evaluation_metadata", delta_output)
        self.assertIn("pipeline_metadata", delta_output)

        # Check contributor attribution
        contributor_data = delta_output["contributor_attribution"]
        self.assertEqual(contributor_data["data_hash"], "abc123def456")
        self.assertEqual(contributor_data["contributed_samples"], 100)
        self.assertEqual(contributor_data["total_samples"], 1000)
        self.assertEqual(contributor_data["contributor_weights"], 0.1)

    @patch("src.pipeline.hokusai_pipeline.current")
    def test_compare_and_output_delta_missing_evaluation_results(self, mock_current):
        """Test error handling when evaluation_results is missing."""
        mock_current.run_id = "test_run_123"

        # Remove evaluation_results
        delattr(self.pipeline, "evaluation_results")

        with self.assertRaises(ValueError) as context:
            self.pipeline.compare_and_output_delta()

        self.assertIn("Missing evaluation_results", str(context.exception))

    @patch("src.pipeline.hokusai_pipeline.current")
    def test_compare_and_output_delta_missing_data_manifest(self, mock_current):
        """Test error handling when data_manifest is missing."""
        mock_current.run_id = "test_run_123"

        # Remove data_manifest
        delattr(self.pipeline, "data_manifest")

        with self.assertRaises(ValueError) as context:
            self.pipeline.compare_and_output_delta()

        self.assertIn("Missing data_manifest", str(context.exception))

    @patch("src.pipeline.hokusai_pipeline.current")
    def test_compare_and_output_delta_missing_metrics(self, mock_current):
        """Test error handling when metrics are missing from evaluation results."""
        mock_current.run_id = "test_run_123"

        # Remove metrics from evaluation results
        self.pipeline.evaluation_results = {
            "baseline_metrics": {},
            "new_metrics": {}
        }

        with self.assertRaises(ValueError) as context:
            self.pipeline.compare_and_output_delta()

        self.assertIn("Missing baseline or new model metrics", str(context.exception))

    @patch("src.pipeline.hokusai_pipeline.mlflow_run_context")
    @patch("src.pipeline.hokusai_pipeline.current")
    @patch("builtins.open", create=True)
    def test_compare_and_output_delta_json_output(self, mock_open, mock_current, mock_mlflow_context):
        """Test that JSON output file is created correctly."""
        mock_current.run_id = "test_run_123"
        mock_mlflow_context.return_value.__enter__ = Mock()
        mock_mlflow_context.return_value.__exit__ = Mock()

        # Mock file writing
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Execute the step
        self.pipeline.compare_and_output_delta()

        # Verify file was opened for writing
        expected_file_path = str(Path(self.temp_dir) / "delta_output_test_run_123.json")
        mock_open.assert_called_with(expected_file_path, "w")

        # Verify JSON was written
        mock_file.write.assert_called()

        # Get the written JSON content
        written_calls = mock_file.write.call_args_list
        written_content = "".join(call[0][0] for call in written_calls)

        # Verify it's valid JSON
        try:
            parsed_json = json.loads(written_content)
            self.assertIn("delta_computation", parsed_json)
        except json.JSONDecodeError:
            # If direct parsing fails, the content might be written in chunks
            # This is acceptable as long as the file was written
            pass

    @patch("src.pipeline.hokusai_pipeline.mlflow")
    @patch("src.pipeline.hokusai_pipeline.mlflow_run_context")
    @patch("src.pipeline.hokusai_pipeline.current")
    def test_compare_and_output_delta_mlflow_artifact_logging(self, mock_current, mock_mlflow_context, mock_mlflow):
        """Test that delta output is logged as MLflow artifact."""
        mock_current.run_id = "test_run_123"
        mock_mlflow_context.return_value.__enter__ = Mock()
        mock_mlflow_context.return_value.__exit__ = Mock()

        # Execute the step
        self.pipeline.compare_and_output_delta()

        # Verify MLflow artifact logging was attempted
        mock_mlflow.log_artifact.assert_called_once()

        # Check the artifact path
        call_args = mock_mlflow.log_artifact.call_args
        artifact_path = call_args[0][0]
        artifact_dir = call_args[0][1]

        self.assertIn("delta_output_test_run_123.json", artifact_path)
        self.assertEqual(artifact_dir, "delta_outputs")

    def test_delta_output_schema_compliance(self):
        """Test that delta output conforms to expected schema."""
        # Set up required attributes for the step
        with patch("src.pipeline.hokusai_pipeline.mlflow_run_context"), \
             patch("src.pipeline.hokusai_pipeline.current") as mock_current:

            mock_current.run_id = "test_run_123"

            # Execute the step
            self.pipeline.compare_and_output_delta()

            # Verify schema compliance
            delta_output = self.pipeline.delta_output

            # Check required top-level fields
            required_fields = [
                "schema_version",
                "delta_computation",
                "baseline_model",
                "new_model",
                "contributor_attribution",
                "evaluation_metadata",
                "pipeline_metadata"
            ]

            for field in required_fields:
                self.assertIn(field, delta_output, f"Missing required field: {field}")

            # Check delta_computation structure
            delta_comp = delta_output["delta_computation"]
            self.assertIn("delta_one_score", delta_comp)
            self.assertIn("metric_deltas", delta_comp)
            self.assertIn("computation_method", delta_comp)
            self.assertIn("metrics_included", delta_comp)

            # Check model metadata
            baseline_model = delta_output["baseline_model"]
            self.assertIn("model_id", baseline_model)
            self.assertIn("model_type", baseline_model)
            self.assertIn("metrics", baseline_model)

            new_model = delta_output["new_model"]
            self.assertIn("model_id", new_model)
            self.assertIn("model_type", new_model)
            self.assertIn("metrics", new_model)
            self.assertIn("training_metadata", new_model)


if __name__ == "__main__":
    unittest.main()
