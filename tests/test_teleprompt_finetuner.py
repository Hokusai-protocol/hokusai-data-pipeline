"""Tests for Teleprompt Fine-tuning Service."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.services.teleprompt_finetuner import (
    TelepromptFinetuner,
    OptimizationConfig,
    OptimizationStrategy,
    OptimizationResult
)


@pytest.fixture
def mock_dspy_program():
    """Create a mock DSPy program."""
    program = Mock()
    program.name = "TestProgram"
    program.version = "1.0.0"
    return program


@pytest.fixture
def optimization_config():
    """Create test optimization config."""
    return OptimizationConfig(
        strategy=OptimizationStrategy.BOOTSTRAP_FEWSHOT,
        min_traces=100,
        max_traces=1000,
        min_quality_score=0.7,
        optimization_rounds=2,
        deltaone_threshold=0.01
    )


@pytest.fixture
def sample_traces():
    """Create sample traces for testing."""
    return [
        {
            "trace_id": f"trace_{i}",
            "inputs": {"text": f"Input {i}"},
            "outputs": {"result": f"Output {i}"},
            "outcome_score": 0.8 + (i % 3) * 0.05,
            "contributor_id": f"contributor_{i % 3}",
            "contributor_address": f"0x{i % 3:040x}",
            "timestamp": datetime.now() - timedelta(hours=i)
        }
        for i in range(150)
    ]


class TestTelepromptFinetuner:
    """Test the TelepromptFinetuner service."""
    
    def test_initialization(self, optimization_config):
        """Test finetuner initialization."""
        finetuner = TelepromptFinetuner(optimization_config)
        
        assert finetuner.config == optimization_config
        assert hasattr(finetuner, 'mlflow_client')
        assert hasattr(finetuner, 'trace_loader')
    
    @patch('src.services.teleprompt_finetuner.TraceLoader')
    def test_load_and_filter_traces(self, mock_trace_loader, optimization_config, mock_dspy_program, sample_traces):
        """Test trace loading and filtering."""
        # Setup mock
        mock_loader_instance = Mock()
        mock_loader_instance.load_traces.return_value = sample_traces
        mock_trace_loader.return_value = mock_loader_instance
        
        finetuner = TelepromptFinetuner(optimization_config)
        
        # Test loading traces
        start_date = datetime.now() - timedelta(days=7)
        end_date = datetime.now()
        
        traces = finetuner._load_and_filter_traces(
            mock_dspy_program,
            start_date,
            end_date,
            "outcome_score"
        )
        
        assert len(traces) == 150
        mock_loader_instance.load_traces.assert_called_once()
    
    def test_calculate_contributor_weights(self, optimization_config, sample_traces):
        """Test contributor weight calculation."""
        finetuner = TelepromptFinetuner(optimization_config)
        
        contributors = finetuner._calculate_contributor_weights(sample_traces)
        
        # Should have 3 contributors (0, 1, 2)
        assert len(contributors) == 3
        
        # Check weights sum to ~1.0
        total_weight = sum(c["weight"] for c in contributors.values())
        assert abs(total_weight - 1.0) < 0.01
        
        # Check contributor data
        for contrib_id, info in contributors.items():
            assert "address" in info
            assert "weight" in info
            assert "trace_count" in info
            assert "avg_score" in info
            assert info["trace_count"] == 50  # 150 traces / 3 contributors
    
    def test_prepare_traces_for_optimization(self, optimization_config, sample_traces):
        """Test trace preparation for teleprompt."""
        finetuner = TelepromptFinetuner(optimization_config)
        
        prepared = finetuner._prepare_traces_for_optimization(sample_traces)
        
        assert len(prepared) == 150
        assert all(isinstance(t, tuple) for t in prepared)
        assert all(len(t) == 2 for t in prepared)
        
        # Check first trace
        inputs, outputs = prepared[0]
        assert inputs == {"text": "Input 0"}
        assert outputs == {"result": "Output 0"}
    
    def test_generate_version(self, optimization_config, mock_dspy_program):
        """Test version generation."""
        finetuner = TelepromptFinetuner(optimization_config)
        
        result = OptimizationResult(
            success=True,
            strategy="bootstrap_fewshot"
        )
        
        version = finetuner._generate_version(mock_dspy_program, result)
        
        # Check version format
        assert version.startswith("1.0.0-opt-boo-")
        assert len(version) > 20  # includes timestamp
    
    def test_evaluate_deltaone_success(self, optimization_config, mock_dspy_program):
        """Test DeltaOne evaluation with success."""
        finetuner = TelepromptFinetuner(optimization_config)
        
        result = OptimizationResult(
            success=True,
            optimized_program=Mock(),
            baseline_program=mock_dspy_program
        )
        
        deltaone_result = finetuner.evaluate_deltaone(result)
        
        assert "deltaone_achieved" in deltaone_result
        assert "delta" in deltaone_result
        assert "baseline_metrics" in deltaone_result
        assert "optimized_metrics" in deltaone_result
    
    def test_evaluate_deltaone_failure(self, optimization_config):
        """Test DeltaOne evaluation with failed optimization."""
        finetuner = TelepromptFinetuner(optimization_config)
        
        result = OptimizationResult(
            success=False,
            error_message="Optimization failed"
        )
        
        deltaone_result = finetuner.evaluate_deltaone(result)
        
        assert deltaone_result["deltaone_achieved"] is False
        assert "error" in deltaone_result
    
    def test_generate_attestation_success(self, optimization_config, mock_dspy_program):
        """Test attestation generation."""
        finetuner = TelepromptFinetuner(optimization_config)
        
        result = OptimizationResult(
            success=True,
            optimized_program=Mock(),
            baseline_program=mock_dspy_program,
            trace_count=1000,
            optimization_time=120.5,
            strategy="bootstrap_fewshot",
            model_version="1.0.0-opt-bfs-20240115120000",
            contributors={
                "contrib1": {
                    "address": "0x1234567890abcdef",
                    "weight": 0.6,
                    "trace_count": 600
                },
                "contrib2": {
                    "address": "0xfedcba0987654321",
                    "weight": 0.4,
                    "trace_count": 400
                }
            },
            metadata={
                "outcome_metric": "engagement_score",
                "date_range": {
                    "start": "2024-01-01T00:00:00",
                    "end": "2024-01-15T00:00:00"
                }
            }
        )
        
        deltaone_result = {
            "deltaone_achieved": True,
            "delta": 0.023,
            "baseline_metrics": {"accuracy": 0.85},
            "optimized_metrics": {"accuracy": 0.873}
        }
        
        attestation = finetuner.generate_attestation(result, deltaone_result)
        
        assert attestation["schema_version"] == "1.0"
        assert attestation["attestation_type"] == "teleprompt_optimization"
        assert "timestamp" in attestation
        assert attestation["performance"]["deltaone_achieved"] is True
        assert attestation["performance"]["performance_delta"] == 0.023
        assert len(attestation["contributors"]) == 2
        assert "attestation_hash" in attestation
    
    def test_generate_attestation_not_achieved(self, optimization_config):
        """Test attestation generation when DeltaOne not achieved."""
        finetuner = TelepromptFinetuner(optimization_config)
        
        result = OptimizationResult(success=True)
        deltaone_result = {"deltaone_achieved": False}
        
        with pytest.raises(ValueError, match="DeltaOne not achieved"):
            finetuner.generate_attestation(result, deltaone_result)
    
    @patch('mlflow.start_run')
    @patch('mlflow.log_params')
    @patch('mlflow.log_dict')
    @patch('mlflow.register_model')
    def test_save_optimized_model(
        self, mock_register, mock_log_dict, mock_log_params, mock_start_run,
        optimization_config, mock_dspy_program
    ):
        """Test saving optimized model to MLflow."""
        # Setup mocks
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__.return_value = mock_run
        
        finetuner = TelepromptFinetuner(optimization_config)
        
        result = OptimizationResult(
            success=True,
            optimized_program=mock_dspy_program,
            strategy="bootstrap_fewshot",
            trace_count=1000,
            optimization_time=120.0,
            model_version="1.0.0-opt-bfs-20240115120000",
            contributors={"contrib1": {"weight": 1.0}}
        )
        
        model_info = finetuner.save_optimized_model(
            result,
            "TestModel-Optimized",
            tags={"deltaone": "true"}
        )
        
        assert model_info["model_name"] == "TestModel-Optimized"
        assert model_info["version"] == "1.0.0-opt-bfs-20240115120000"
        assert model_info["run_id"] == "test_run_id"
        assert "deltaone" in model_info["tags"]
        
        mock_log_params.assert_called_once()
        assert mock_log_dict.call_count == 2  # contributors and metadata
        mock_register.assert_called_once()
    
    @patch('src.services.teleprompt_finetuner.DSPY_AVAILABLE', True)
    @patch('src.services.teleprompt_finetuner.TraceLoader')
    def test_run_optimization_insufficient_traces(
        self, mock_trace_loader, optimization_config, mock_dspy_program
    ):
        """Test optimization with insufficient traces."""
        # Setup mock with too few traces
        mock_loader_instance = Mock()
        mock_loader_instance.load_traces.return_value = [{"trace": i} for i in range(50)]
        mock_trace_loader.return_value = mock_loader_instance
        
        finetuner = TelepromptFinetuner(optimization_config)
        
        result = finetuner.run_optimization(
            mock_dspy_program,
            datetime.now() - timedelta(days=7),
            datetime.now()
        )
        
        assert result.success is False
        assert "Insufficient traces" in result.error_message
    
    def test_optimization_config_validation(self):
        """Test optimization config validation."""
        # Test invalid min/max traces
        with pytest.raises(ValueError):
            OptimizationConfig(min_traces=1000, max_traces=500)
        
        # Test invalid quality score
        with pytest.raises(ValueError):
            OptimizationConfig(min_quality_score=1.5)
        
        # Test negative deltaone threshold
        with pytest.raises(ValueError):
            OptimizationConfig(deltaone_threshold=-0.01)


class TestOptimizationStrategy:
    """Test optimization strategy enum."""
    
    def test_strategy_values(self):
        """Test strategy enum values."""
        assert OptimizationStrategy.BOOTSTRAP_FEWSHOT.value == "bootstrap_fewshot"
        assert OptimizationStrategy.BOOTSTRAP_FEWSHOT_RANDOM.value == "bootstrap_fewshot_random"
        assert OptimizationStrategy.COPRO.value == "copro"
        assert OptimizationStrategy.MIPRO.value == "mipro"