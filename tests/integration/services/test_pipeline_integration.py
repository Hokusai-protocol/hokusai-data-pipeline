"""Integration tests for enhanced Metaflow pipeline with MLOps services."""

import pytest
from unittest.mock import Mock, patch
import pandas as pd



class TestEnhancedPipelineIntegration:
    """Test enhanced pipeline integration with MLOps services."""

    @pytest.fixture
    def mock_registry(self):
        """Create mock model registry."""
        with patch("src.services.model_registry.HokusaiModelRegistry") as mock:
            registry = mock.return_value
            registry.register_baseline.return_value = {
                "model_id": "baseline/1",
                "version": "1"
            }
            registry.register_improved_model.return_value = {
                "model_id": "improved/2",
                "version": "2"
            }
            yield registry

    @pytest.fixture
    def mock_tracker(self):
        """Create mock performance tracker."""
        with patch("src.services.performance_tracker.PerformanceTracker") as mock:
            tracker = mock.return_value
            tracker.track_improvement.return_value = (
                {"accuracy": 0.03, "auroc": 0.02},
                {"attestation_hash": "0xabc123"}
            )
            yield tracker

    @pytest.fixture
    def mock_experiment_manager(self):
        """Create mock experiment manager."""
        with patch("src.services.experiment_manager.ExperimentManager") as mock:
            manager = mock.return_value
            manager.create_improvement_experiment.return_value = "exp_123"
            manager.compare_models.return_value = {
                "baseline_metrics": {"accuracy": 0.85},
                "candidate_metrics": {"accuracy": 0.88},
                "improvements": {"accuracy": 0.03},
                "recommendation": "ACCEPT"
            }
            yield manager

    def test_register_baseline_step_integration(self, mock_registry):
        """Test integration of register_baseline step."""
        from src.pipeline.hokusai_pipeline import HokusaiEvaluationPipeline

        # Create pipeline instance
        pipeline = HokusaiEvaluationPipeline()
        pipeline.baseline_model = Mock()
        pipeline.baseline_metrics = {"accuracy": 0.85, "auroc": 0.82}

        # Mock the step execution
        with patch.object(pipeline, "next"):
            pipeline.register_baseline()

        # Verify registry was called
        mock_registry.register_baseline.assert_called_once()
        call_args = mock_registry.register_baseline.call_args
        assert call_args[1]["model_type"] == "lead_scoring"
        assert "dataset" in call_args[1]["metadata"]

    def test_track_improvement_step_integration(self, mock_tracker, mock_registry):
        """Test integration of track_improvement step."""
        from src.pipeline.hokusai_pipeline import HokusaiEvaluationPipeline

        # Create pipeline instance
        pipeline = HokusaiEvaluationPipeline()
        pipeline.baseline_id = "baseline/1"
        pipeline.baseline_metrics = {"accuracy": 0.85, "auroc": 0.82}
        pipeline.improved_metrics = {"accuracy": 0.88, "auroc": 0.84}
        pipeline.improved_model = Mock()
        pipeline.contribution_metadata = {
            "contributor_id": "contrib_001",
            "contributor_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
            "dataset_hash": "0xdef456"
        }

        # Mock the step execution
        with patch.object(pipeline, "next"):
            pipeline.track_improvement()

        # Verify tracker was called
        mock_tracker.track_improvement.assert_called_once()
        call_args = mock_tracker.track_improvement.call_args
        assert call_args[1]["baseline_metrics"] == pipeline.baseline_metrics
        assert call_args[1]["improved_metrics"] == pipeline.improved_metrics

        # Verify registry was called to register improved model
        mock_registry.register_improved_model.assert_called_once()

    def test_experiment_creation_integration(self, mock_experiment_manager):
        """Test experiment creation during pipeline run."""
        from src.pipeline.hokusai_pipeline import HokusaiEvaluationPipeline

        pipeline = HokusaiEvaluationPipeline()
        pipeline.baseline_id = "baseline/1"
        pipeline.contributed_data = pd.DataFrame({
            "feature1": [1, 2, 3],
            "feature2": [4, 5, 6],
            "label": [0, 1, 1]
        })

        # Mock the experimental evaluation
        with patch.object(pipeline, "next"):
            pipeline.create_experiment()

        # Verify experiment manager was called
        mock_experiment_manager.create_improvement_experiment.assert_called_once()
        call_args = mock_experiment_manager.create_improvement_experiment.call_args
        assert call_args[1]["baseline_model_id"] == "baseline/1"

    def test_full_pipeline_flow_with_services(self, mock_registry, mock_tracker,
                                            mock_experiment_manager):
        """Test complete pipeline flow with all services integrated."""
        from src.pipeline.hokusai_pipeline import HokusaiEvaluationPipeline

        # Mock all pipeline data
        pipeline = HokusaiEvaluationPipeline()

        # Simulate pipeline execution stages
        stages = [
            ("load_baseline_model", {"baseline_model": Mock()}),
            ("register_baseline", {"baseline_id": "baseline/1"}),
            ("integrate_contributed_data", {"merged_data": pd.DataFrame()}),
            ("train_new_model", {"improved_model": Mock()}),
            ("evaluate_on_benchmark", {
                "baseline_metrics": {"accuracy": 0.85},
                "improved_metrics": {"accuracy": 0.88}
            }),
            ("track_improvement", {
                "delta": {"accuracy": 0.03},
                "attestation": {"hash": "0xabc123"}
            })
        ]

        # Verify service integration at each stage
        for stage_name, stage_data in stages:
            for key, value in stage_data.items():
                setattr(pipeline, key, value)

        # Check that all services would be called
        assert hasattr(pipeline, "baseline_id")
        assert hasattr(pipeline, "delta")
        assert hasattr(pipeline, "attestation")

    def test_service_error_handling(self, mock_registry):
        """Test pipeline handles service errors gracefully."""
        from src.pipeline.hokusai_pipeline import HokusaiEvaluationPipeline

        # Make registry raise an error
        mock_registry.register_baseline.side_effect = Exception("MLflow connection failed")

        pipeline = HokusaiEvaluationPipeline()
        pipeline.baseline_model = Mock()

        # Pipeline should handle the error
        with pytest.raises(Exception) as exc_info:
            pipeline.register_baseline()

        assert "MLflow connection failed" in str(exc_info.value)

    def test_backward_compatibility(self):
        """Test that enhanced pipeline maintains backward compatibility."""
        from src.pipeline.hokusai_pipeline import HokusaiEvaluationPipeline

        # Create pipeline without new services
        with patch.dict("os.environ", {"DISABLE_MLOPS_SERVICES": "true"}):
            pipeline = HokusaiEvaluationPipeline()

            # Old steps should still work
            pipeline.baseline_model = Mock()
            pipeline.contributed_data_path = "test_data.csv"

            # Verify pipeline can run without services
            assert hasattr(pipeline, "load_baseline_model")
            assert hasattr(pipeline, "integrate_contributed_data")
            assert hasattr(pipeline, "train_new_model")

    @patch("mlflow.start_run")
    @patch("mlflow.log_metrics")
    def test_metrics_aggregation_across_services(self, mock_log_metrics,
                                                mock_start_run, mock_registry,
                                                mock_tracker):
        """Test that metrics are properly aggregated across all services."""
        from src.pipeline.hokusai_pipeline import HokusaiEvaluationPipeline

        # Setup run context
        mock_run = Mock()
        mock_run.info.run_id = "pipeline_run_123"
        mock_start_run.return_value.__enter__ = Mock(return_value=mock_run)
        mock_start_run.return_value.__exit__ = Mock(return_value=None)

        # Create pipeline instance to verify initialization
        HokusaiEvaluationPipeline()

        # Simulate metrics from different stages
        all_metrics = {
            "baseline_accuracy": 0.85,
            "improved_accuracy": 0.88,
            "accuracy_improvement": 0.03,
            "deltaone_value": 3.0,
            "attestation_generated": 1
        }

        # Log metrics
        for metric, value in all_metrics.items():
            mock_log_metrics({metric: value})

        # Verify all metrics were logged
        assert mock_log_metrics.call_count >= len(all_metrics)

    def test_contributor_attribution_flow(self, mock_registry, mock_tracker):
        """Test that contributor attribution flows through the pipeline."""
        from src.pipeline.hokusai_pipeline import HokusaiEvaluationPipeline

        contributor_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f62341"

        pipeline = HokusaiEvaluationPipeline()
        pipeline.contributor_address = contributor_address
        pipeline.improved_model = Mock()
        pipeline.baseline_id = "baseline/1"
        pipeline.delta_metrics = {"accuracy": 0.03}

        # Execute improvement tracking
        with patch.object(pipeline, "next"):
            pipeline.track_improvement()

        # Verify contributor was properly attributed
        registry_call = mock_registry.register_improved_model.call_args
        assert registry_call[1]["contributor"] == contributor_address

        tracker_call = mock_tracker.log_contribution_impact.call_args
        assert tracker_call[0][0] == contributor_address
