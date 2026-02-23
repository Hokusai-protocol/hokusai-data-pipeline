"""Unit tests for Teleprompt Fine-tuning Service."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.services.teleprompt_finetuner import (
    OptimizationConfig,
    OptimizationResult,
    OptimizationStrategy,
    TelepromptFinetuner,
)


class TestOptimizationConfig:
    """Test cases for OptimizationConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = OptimizationConfig()

        assert config.strategy == OptimizationStrategy.BOOTSTRAP_FEWSHOT
        assert config.min_traces == 1000
        assert config.max_traces == 100000
        assert config.min_quality_score == 0.7
        assert config.optimization_rounds == 3
        assert config.timeout_seconds == 7200  # 2 hours
        assert config.enable_deltaone_check is True
        assert config.deltaone_threshold == 0.01  # 1%

    def test_custom_config(self):
        """Test custom configuration."""
        config = OptimizationConfig(
            strategy=OptimizationStrategy.BOOTSTRAP_FEWSHOT_RANDOM,
            min_traces=500,
            optimization_rounds=5,
            deltaone_threshold=0.02,
        )

        assert config.strategy == OptimizationStrategy.BOOTSTRAP_FEWSHOT_RANDOM
        assert config.min_traces == 500
        assert config.optimization_rounds == 5
        assert config.deltaone_threshold == 0.02

    def test_config_validation(self):
        """Test configuration validation."""
        # Valid config
        config = OptimizationConfig(min_traces=100, max_traces=1000)
        assert config.min_traces < config.max_traces

        # Invalid config
        with pytest.raises(ValueError, match="min_traces must be less than max_traces"):
            OptimizationConfig(min_traces=1000, max_traces=100)

        with pytest.raises(ValueError, match="min_quality_score must be between 0 and 1"):
            OptimizationConfig(min_quality_score=1.5)


class TestTelepromptFinetuner:
    """Test cases for TelepromptFinetuner service."""

    @pytest.fixture
    def mock_mlflow(self):
        """Mock MLflow client."""
        with patch("mlflow.tracking.MlflowClient") as mock:
            yield mock

    @pytest.fixture
    def mock_trace_loader(self):
        """Mock trace loader."""
        with patch("src.services.teleprompt_finetuner.TraceLoader") as mock:
            yield mock

    def test_initialization(self):
        """Test finetuner initialization."""
        config = OptimizationConfig()
        finetuner = TelepromptFinetuner(config)

        assert finetuner.config == config
        assert finetuner.mlflow_client is not None

    def test_run_optimization_success(self, mock_mlflow, mock_trace_loader):
        """Test successful optimization run."""
        # Setup mocks
        mock_traces = [
            {
                "inputs": {"text": "Hello"},
                "outputs": {"response": "Hi there"},
                "outcome_score": 0.9,
                "contributor_id": "contributor1",
                "contributor_address": "0x123...",
            }
        ] * 1000

        mock_trace_loader.return_value.load_traces.return_value = mock_traces

        # Mock DSPy program
        mock_program = Mock()
        mock_program.name = "TestProgram"

        # Mock optimization internals
        with patch.object(TelepromptFinetuner, "_run_teleprompt_compilation") as mock_compile:
            with patch.object(TelepromptFinetuner, "_generate_version", return_value="1.0.0-opt"):
                mock_optimized = Mock()
                mock_compile.return_value = mock_optimized

                finetuner = TelepromptFinetuner(OptimizationConfig())
                result = finetuner.run_optimization(
                    program=mock_program,
                    start_date=datetime.now() - timedelta(days=7),
                    end_date=datetime.now(),
                )

                assert result.success is True
                assert result.optimized_program == mock_optimized
                assert result.trace_count == 1000
                assert result.optimization_time > 0

    def test_run_optimization_insufficient_traces(self, mock_trace_loader):
        """Test optimization with insufficient traces."""
        # Setup mock with too few traces
        mock_traces = [{"inputs": {}, "outputs": {}, "outcome_score": 0.8}] * 100
        mock_trace_loader.return_value.load_traces.return_value = mock_traces

        finetuner = TelepromptFinetuner(OptimizationConfig(min_traces=1000))

        result = finetuner.run_optimization(
            program=Mock(),
            start_date=datetime.now() - timedelta(days=7),
            end_date=datetime.now(),
        )

        assert result.success is False
        assert "Insufficient traces" in (result.error_message or "")

    def test_deltaone_evaluation(self):
        """Test DeltaOne evaluation after optimization."""
        config = OptimizationConfig(enable_deltaone_check=True)
        finetuner = TelepromptFinetuner(config)

        # Mock successful optimization
        optimization_result = OptimizationResult(
            success=True,
            optimized_program=Mock(),
            baseline_program=Mock(),
            trace_count=1000,
            optimization_time=60.0,
            strategy="bootstrap_fewshot",
        )

        # Evaluate DeltaOne
        deltaone_result = finetuner.evaluate_deltaone(optimization_result)

        assert deltaone_result["deltaone_achieved"] is True
        assert deltaone_result["delta"] == pytest.approx(0.03)

    def test_contributor_attribution(self, mock_trace_loader):
        """Test contributor attribution tracking."""
        # Setup traces with different contributors
        mock_traces = [
            {
                "inputs": {"text": "Test"},
                "outputs": {"response": "Response"},
                "outcome_score": 0.9,
                "contributor_id": "contributor1",
                "contributor_address": "0x111...",
            }
        ] * 600

        mock_traces.extend(
            [
                {
                    "inputs": {"text": "Test2"},
                    "outputs": {"response": "Response2"},
                    "outcome_score": 0.85,
                    "contributor_id": "contributor2",
                    "contributor_address": "0x222...",
                }
            ]
            * 400
        )

        mock_trace_loader.return_value.load_traces.return_value = mock_traces

        finetuner = TelepromptFinetuner(OptimizationConfig())

        # Track contributors
        contributors = finetuner._calculate_contributor_weights(mock_traces)

        assert len(contributors) == 2
        assert contributors["contributor1"]["weight"] == 0.6
        assert contributors["contributor1"]["address"] == "0x111..."
        assert contributors["contributor2"]["weight"] == 0.4
        assert contributors["contributor2"]["address"] == "0x222..."

    def test_attestation_generation(self):
        """Test attestation generation for DeltaOne achievement."""
        finetuner = TelepromptFinetuner(OptimizationConfig())

        # Create optimization result
        optimization_result = OptimizationResult(
            success=True,
            optimized_program=Mock(),
            baseline_program=Mock(version="1.0.0"),
            trace_count=1000,
            optimization_time=60.0,
            strategy="bootstrap_fewshot",
            model_version="1.0.0-opt",
            contributors={
                "contributor1": {"address": "0x111...", "weight": 0.6, "trace_count": 600},
                "contributor2": {"address": "0x222...", "weight": 0.4, "trace_count": 400},
            },
        )

        # Create DeltaOne result
        deltaone_result = {
            "deltaone_achieved": True,
            "delta": 0.02,
            "baseline_metrics": {"accuracy": 0.85, "f1": 0.83},
            "optimized_metrics": {"accuracy": 0.87, "f1": 0.85},
        }

        # Generate attestation
        attestation = finetuner.generate_attestation(optimization_result, deltaone_result)

        assert attestation["schema_version"] == "1.0"
        assert attestation["attestation_type"] == "teleprompt_optimization"
        assert attestation["performance"]["deltaone_achieved"] is True
        assert attestation["performance"]["performance_delta"] == 0.02
        assert len(attestation["contributors"]) == 2
        assert attestation["contributors"][0]["address"] == "0x111..."
        assert attestation["contributors"][0]["weight"] == 0.6
        assert "attestation_hash" in attestation

    def test_optimization_timeout(self, mock_trace_loader):
        """Test optimization timeout handling."""
        # Setup mock traces
        mock_traces = [{"inputs": {}, "outputs": {}, "outcome_score": 0.8}] * 1000
        mock_trace_loader.return_value.load_traces.return_value = mock_traces

        with patch.object(TelepromptFinetuner, "_run_teleprompt_compilation") as mock_compile:
            mock_compile.side_effect = TimeoutError("Optimization timed out")
            config = OptimizationConfig(timeout_seconds=1)
            finetuner = TelepromptFinetuner(config)

            result = finetuner.run_optimization(
                program=Mock(),
                start_date=datetime.now() - timedelta(days=7),
                end_date=datetime.now(),
            )
            assert result.success is False
            assert "Optimization timed out" in (result.error_message or "")

    def test_save_optimized_model(self, mock_mlflow):
        """Test saving optimized model to MLflow."""
        finetuner = TelepromptFinetuner(OptimizationConfig())

        # Create optimization result
        optimization_result = OptimizationResult(
            success=True,
            optimized_program=Mock(),
            baseline_program=Mock(),
            trace_count=1000,
            optimization_time=60.0,
            strategy="bootstrap_fewshot",
            model_version="1.0.0-optimized",
        )

        # Save model
        with patch("mlflow.start_run") as mock_run:
            with patch("mlflow.register_model") as mock_register_model:
                with patch("mlflow.log_params"):
                    with patch("mlflow.log_dict"):
                        mock_run_context = MagicMock()
                        mock_run_context.info.run_id = "test_run_123"
                        mock_run.return_value.__enter__.return_value = mock_run_context

                        model_info = finetuner.save_optimized_model(
                            optimization_result, model_name="TestModel"
                        )

                        assert model_info["model_name"] == "TestModel"
                        assert model_info["version"] == "1.0.0-optimized"
                        assert model_info["run_id"] == "test_run_123"
                        mock_register_model.assert_called_once()
