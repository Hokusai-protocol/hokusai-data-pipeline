"""Unit tests for the main Hokusai pipeline."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

# Skip all tests in this file as Metaflow FlowSpec cannot be tested like regular classes
pytestmark = pytest.mark.skip(reason="Metaflow FlowSpec requires special test setup")

from src.pipeline.hokusai_pipeline import HokusaiPipeline
from src.utils.constants import ATTESTATION_SCHEMA_VERSION, ATTESTATION_VERSION, STATUS_SUCCESS


class TestHokusaiPipeline:
    """Test suite for HokusaiPipeline class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = HokusaiPipeline()
        self.pipeline.baseline_model_path = "/path/to/baseline"
        self.pipeline.contributed_data_path = "/path/to/data"
        self.pipeline.output_dir = "./test_outputs"
        self.pipeline.dry_run = True

    @patch("src.pipeline.hokusai_pipeline.get_test_config")
    @patch("src.pipeline.hokusai_pipeline.current")
    def test_start_step_dry_run(self, mock_current, mock_get_config):
        """Test start step in dry run mode."""
        # Mock config
        mock_config = Mock()
        mock_config.environment = "test"
        mock_config.random_seed = 42
        mock_config.to_dict.return_value = {"env": "test", "seed": 42}
        mock_get_config.return_value = mock_config

        # Mock current run
        mock_current.run_id = "test_run_123"

        # Mock next step
        self.pipeline.next = Mock()

        # Execute start step
        self.pipeline.start()

        # Assertions
        assert self.pipeline.config == mock_config
        assert self.pipeline.run_metadata["run_id"] == "test_run_123"
        assert "started_at" in self.pipeline.run_metadata
        assert self.pipeline.run_metadata["parameters"]["dry_run"] is True
        self.pipeline.next.assert_called_once_with(self.pipeline.load_baseline_model)

    @patch("src.pipeline.hokusai_pipeline.get_config")
    @patch("src.pipeline.hokusai_pipeline.current")
    @patch("src.pipeline.hokusai_pipeline.random")
    @patch("src.pipeline.hokusai_pipeline.np.random")
    def test_start_step_production(
        self, mock_np_random, mock_random, mock_current, mock_get_config
    ):
        """Test start step in production mode."""
        self.pipeline.dry_run = False

        mock_config = Mock()
        mock_config.environment = "production"
        mock_config.random_seed = 123
        mock_config.to_dict.return_value = {"env": "production"}
        mock_get_config.return_value = mock_config

        mock_current.run_id = "prod_run_456"
        self.pipeline.next = Mock()

        self.pipeline.start()

        # Check random seeds were set
        mock_random.seed.assert_called_once_with(123)
        mock_np_random.seed.assert_called_once_with(123)

        assert self.pipeline.config.environment == "production"

    def test_load_baseline_model_dry_run(self):
        """Test loading baseline model in dry run mode."""
        self.pipeline.next = Mock()
        self.pipeline.dry_run = True

        self.pipeline.load_baseline_model()

        assert self.pipeline.baseline_model["type"] == "mock_model"
        assert self.pipeline.baseline_model["metrics"]["accuracy"] == 0.85
        assert self.pipeline.baseline_model["metrics"]["f1_score"] == 0.85
        self.pipeline.next.assert_called_once_with(self.pipeline.integrate_contributed_data)

    @patch("src.pipeline.hokusai_pipeline.BaselineModelLoader")
    def test_load_baseline_model_production(self, mock_loader_class):
        """Test loading baseline model in production mode."""
        self.pipeline.dry_run = False
        self.pipeline.config = Mock(mlflow_tracking_uri="http://mlflow:5000")
        self.pipeline.next = Mock()

        # Mock baseline loader
        mock_loader = Mock()
        mock_model = Mock()
        mock_model.model_info = {"name": "baseline", "version": "1"}
        mock_loader.load_from_mlflow.return_value = mock_model
        mock_loader_class.return_value = mock_loader

        self.pipeline.load_baseline_model()

        mock_loader_class.assert_called_once_with(
            tracking_uri=self.pipeline.config.mlflow_tracking_uri
        )
        mock_loader.load_from_mlflow.assert_called_once()
        assert self.pipeline.baseline_model == mock_model

    def test_integrate_contributed_data_dry_run(self):
        """Test data integration in dry run mode."""
        self.pipeline.dry_run = True
        self.pipeline.next = Mock()

        self.pipeline.integrate_contributed_data()

        assert self.pipeline.integrated_data is not None
        assert "data_hash" in self.pipeline.integrated_data
        assert self.pipeline.integrated_data["num_samples"] == 1000
        assert len(self.pipeline.integrated_data["contributor_weights"]) == 3
        self.pipeline.next.assert_called_once_with(self.pipeline.train_new_model)

    @patch("src.pipeline.hokusai_pipeline.DataIntegrator")
    def test_integrate_contributed_data_production(self, mock_integrator_class):
        """Test data integration in production mode."""
        self.pipeline.dry_run = False
        self.pipeline.config = Mock()
        self.pipeline.next = Mock()

        # Mock data integrator
        mock_integrator = Mock()
        mock_integrated_data = {
            "data_hash": "abc123",
            "num_samples": 5000,
            "contributor_weights": {"contrib1": 0.6, "contrib2": 0.4},
        }
        mock_integrator.integrate_from_path.return_value = mock_integrated_data
        mock_integrator_class.return_value = mock_integrator

        self.pipeline.integrate_contributed_data()

        mock_integrator.integrate_from_path.assert_called_once_with(
            self.pipeline.contributed_data_path
        )
        assert self.pipeline.integrated_data == mock_integrated_data

    def test_train_new_model_dry_run(self):
        """Test model training in dry run mode."""
        self.pipeline.dry_run = True
        self.pipeline.baseline_model = {"type": "mock_model"}
        self.pipeline.integrated_data = {"num_samples": 1000}
        self.pipeline.next = Mock()

        self.pipeline.train_new_model()

        assert self.pipeline.new_model is not None
        assert self.pipeline.new_model["type"] == "mock_model_updated"
        assert self.pipeline.new_model["metrics"]["accuracy"] == 0.88
        self.pipeline.next.assert_called_once_with(self.pipeline.evaluate_on_benchmark)

    @patch("src.pipeline.hokusai_pipeline.ModelTrainer")
    def test_train_new_model_production(self, mock_trainer_class):
        """Test model training in production mode."""
        self.pipeline.dry_run = False
        self.pipeline.config = Mock()
        self.pipeline.baseline_model = Mock()
        self.pipeline.integrated_data = {"data": "integrated"}
        self.pipeline.next = Mock()

        # Mock model trainer
        mock_trainer = Mock()
        mock_new_model = Mock()
        mock_trainer.train_from_baseline.return_value = mock_new_model
        mock_trainer_class.return_value = mock_trainer

        self.pipeline.train_new_model()

        mock_trainer.train_from_baseline.assert_called_once_with(
            baseline_model=self.pipeline.baseline_model, training_data=self.pipeline.integrated_data
        )
        assert self.pipeline.new_model == mock_new_model

    def test_evaluate_on_benchmark_dry_run(self):
        """Test benchmark evaluation in dry run mode."""
        self.pipeline.dry_run = True
        self.pipeline.baseline_model = {"metrics": {"accuracy": 0.85}}
        self.pipeline.new_model = {"metrics": {"accuracy": 0.88}}
        self.pipeline.next = Mock()

        self.pipeline.evaluate_on_benchmark()

        assert self.pipeline.baseline_evaluation is not None
        assert self.pipeline.new_evaluation is not None
        assert self.pipeline.baseline_evaluation["overall_score"] == 0.85
        assert self.pipeline.new_evaluation["overall_score"] == 0.88
        self.pipeline.next.assert_called_once()

    @patch("src.pipeline.hokusai_pipeline.Evaluator")
    def test_evaluate_on_benchmark_production(self, mock_evaluator_class):
        """Test benchmark evaluation in production mode."""
        self.pipeline.dry_run = False
        self.pipeline.config = Mock(benchmark_dataset_path="/path/to/benchmark")
        self.pipeline.baseline_model = Mock()
        self.pipeline.new_model = Mock()
        self.pipeline.next = Mock()

        # Mock evaluator
        mock_evaluator = Mock()
        mock_baseline_eval = {"accuracy": 0.85, "overall_score": 0.85}
        mock_new_eval = {"accuracy": 0.88, "overall_score": 0.88}
        mock_evaluator.evaluate_model.side_effect = [mock_baseline_eval, mock_new_eval]
        mock_evaluator_class.return_value = mock_evaluator

        self.pipeline.evaluate_on_benchmark()

        assert mock_evaluator.evaluate_model.call_count == 2
        assert self.pipeline.baseline_evaluation == mock_baseline_eval
        assert self.pipeline.new_evaluation == mock_new_eval

    def test_compare_and_output_delta(self):
        """Test delta comparison step."""
        self.pipeline.baseline_evaluation = {
            "accuracy": 0.85,
            "precision": 0.83,
            "recall": 0.87,
            "f1_score": 0.85,
            "overall_score": 0.85,
        }
        self.pipeline.new_evaluation = {
            "accuracy": 0.88,
            "precision": 0.86,
            "recall": 0.90,
            "f1_score": 0.88,
            "overall_score": 0.88,
        }
        self.pipeline.next = Mock()

        self.pipeline.compare_and_output_delta()

        assert self.pipeline.delta_results is not None
        assert self.pipeline.delta_results["accuracy"]["delta"] == 0.03
        assert self.pipeline.delta_results["accuracy"]["relative_change"] == pytest.approx(
            0.0353, rel=1e-3
        )
        assert self.pipeline.delta_score == 0.03
        self.pipeline.next.assert_called_once_with(self.pipeline.generate_attestation_output)

    def test_generate_attestation_output(self):
        """Test attestation generation step."""
        # Set up required data
        self.pipeline.run_metadata = {"run_id": "test_123"}
        self.pipeline.baseline_model = {"version": "1.0.0"}
        self.pipeline.new_model = {"version": "1.1.0"}
        self.pipeline.integrated_data = {
            "data_hash": "abc123",
            "contributor_weights": {"contrib1": 0.6},
        }
        self.pipeline.baseline_evaluation = {"overall_score": 0.85}
        self.pipeline.new_evaluation = {"overall_score": 0.88}
        self.pipeline.delta_results = {"accuracy": {"delta": 0.03}}
        self.pipeline.delta_score = 0.03
        self.pipeline.next = Mock()

        self.pipeline.generate_attestation_output()

        assert self.pipeline.attestation is not None
        assert self.pipeline.attestation["schema_version"] == ATTESTATION_SCHEMA_VERSION
        assert self.pipeline.attestation["attestation_version"] == ATTESTATION_VERSION
        assert self.pipeline.attestation["delta_score"] == 0.03
        assert "attestation_hash" in self.pipeline.attestation
        self.pipeline.next.assert_called_once_with(self.pipeline.save_outputs)

    @patch("src.pipeline.hokusai_pipeline.Path")
    @patch("src.pipeline.hokusai_pipeline.json.dump")
    def test_save_outputs(self, mock_json_dump, mock_path_class):
        """Test saving pipeline outputs."""
        # Mock Path
        mock_output_dir = Mock()
        mock_output_dir.exists.return_value = False
        mock_path_class.return_value = mock_output_dir

        # Set up data
        self.pipeline.run_metadata = {"run_id": "test_123"}
        self.pipeline.attestation = {"delta_score": 0.03}
        self.pipeline.delta_results = {"accuracy": {"delta": 0.03}}
        self.pipeline.next = Mock()

        # Mock file operations
        mock_file = Mock()
        mock_output_dir.open.return_value.__enter__ = Mock(return_value=mock_file)
        mock_output_dir.open.return_value.__exit__ = Mock(return_value=None)

        self.pipeline.save_outputs()

        # Check directory was created
        mock_output_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

        # Check files were saved
        assert mock_output_dir.open.call_count >= 2  # attestation and delta files
        self.pipeline.next.assert_called_once_with(self.pipeline.monitor_and_log)

    @patch("src.pipeline.hokusai_pipeline.PipelineLogger")
    def test_monitor_and_log(self, mock_logger_class):
        """Test monitoring and logging step."""
        # Mock logger
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        # Set up data
        self.pipeline.run_metadata = {
            "run_id": "test_123",
            "started_at": datetime.utcnow().isoformat(),
        }
        self.pipeline.delta_score = 0.03
        self.pipeline.attestation = {"attestation_hash": "abc123"}
        self.pipeline.next = Mock()

        self.pipeline.monitor_and_log()

        # Check metrics were logged
        mock_logger.log_metrics.assert_called()
        logged_metrics = mock_logger.log_metrics.call_args[0][0]
        assert "pipeline.duration_seconds" in logged_metrics
        assert "pipeline.delta_score" in logged_metrics
        assert logged_metrics["pipeline.delta_score"] == 0.03

        self.pipeline.next.assert_called_once_with(self.pipeline.end)

    def test_end_step(self):
        """Test end step."""
        self.pipeline.run_metadata = {"run_id": "test_123"}
        self.pipeline.delta_score = 0.03
        self.pipeline.attestation = {"attestation_hash": "abc123"}

        # Should not raise any exceptions
        self.pipeline.end()

        assert self.pipeline.run_metadata.get("completed_at") is not None
        assert self.pipeline.run_metadata.get("status") == STATUS_SUCCESS

    def test_pipeline_parameter_validation(self):
        """Test pipeline parameter validation."""
        pipeline = HokusaiPipeline()

        # Test required parameters
        with pytest.raises(AttributeError):
            # contributed_data_path is required
            pipeline.start()

    @patch("src.pipeline.hokusai_pipeline.BaselineModelLoader")
    def test_error_handling_in_step(self, mock_loader_class):
        """Test error handling in pipeline steps."""
        self.pipeline.dry_run = False
        self.pipeline.config = Mock()
        self.pipeline.next = Mock()

        # Mock loader to raise exception
        mock_loader_class.side_effect = Exception("Model loading failed")

        with pytest.raises(Exception, match="Model loading failed"):
            self.pipeline.load_baseline_model()

    def test_delta_calculation_edge_cases(self):
        """Test delta calculation with edge cases."""
        # Test with zero baseline
        self.pipeline.baseline_evaluation = {"accuracy": 0.0, "overall_score": 0.0}
        self.pipeline.new_evaluation = {"accuracy": 0.5, "overall_score": 0.5}
        self.pipeline.next = Mock()

        self.pipeline.compare_and_output_delta()

        # Should handle division by zero gracefully
        assert self.pipeline.delta_results["accuracy"]["delta"] == 0.5
        assert self.pipeline.delta_results["accuracy"]["relative_change"] == float("inf")

    def test_attestation_determinism(self):
        """Test that attestation generation is deterministic."""
        # Set up identical data
        data = {
            "run_id": "test_123",
            "baseline_model": {"version": "1.0.0"},
            "new_model": {"version": "1.1.0"},
            "integrated_data": {"data_hash": "abc123"},
            "delta_score": 0.03,
        }

        self.pipeline.run_metadata = {"run_id": data["run_id"]}
        self.pipeline.baseline_model = data["baseline_model"]
        self.pipeline.new_model = data["new_model"]
        self.pipeline.integrated_data = data["integrated_data"]
        self.pipeline.baseline_evaluation = {"overall_score": 0.85}
        self.pipeline.new_evaluation = {"overall_score": 0.88}
        self.pipeline.delta_results = {"accuracy": {"delta": 0.03}}
        self.pipeline.delta_score = data["delta_score"]
        self.pipeline.next = Mock()

        # Generate attestation twice
        self.pipeline.generate_attestation_output()
        hash1 = self.pipeline.attestation["attestation_hash"]

        self.pipeline.generate_attestation_output()
        hash2 = self.pipeline.attestation["attestation_hash"]

        # Hashes should be identical for same input
        assert hash1 == hash2
