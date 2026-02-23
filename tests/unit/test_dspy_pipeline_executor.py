"""Unit tests for DSPyPipelineExecutor."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.services.dspy_pipeline_executor import (
    DSPyPipelineExecutor,
    ExecutionMode,
    ExecutionResult,
    ValidationError,
)


class MockDSPySignature:
    """Mock DSPy signature for testing."""

    def __init__(self, input_fields: list, output_fields: list):
        self.input_fields = input_fields
        self.output_fields = output_fields


class MockDSPyProgram:
    """Mock DSPy program for testing."""

    def __init__(self, name: str = "test_program"):
        self.name = name
        self.signature = MockDSPySignature(
            input_fields=["input1", "input2"], output_fields=["output"]
        )
        self._call_count = 0
        self._should_fail = False

    def forward(self, input1=None, input2=None, **kwargs):
        """Mock forward method."""
        self._call_count += 1
        if self._should_fail:
            raise Exception("Mock execution error")
        # Handle both keyword args and positional
        input_val = input1 or kwargs.get("input1", "")
        return {"output": f"processed_{input_val}"}

    def __call__(self, **kwargs):
        """Make program callable."""
        return self.forward(**kwargs)


class TestDSPyPipelineExecutor:
    """Test cases for DSPyPipelineExecutor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = DSPyPipelineExecutor()
        self.mock_program = MockDSPyProgram()

    def test_initialization(self):
        """Test executor initialization."""
        # Default initialization
        executor = DSPyPipelineExecutor()
        assert executor.cache_enabled is True
        assert executor.mlflow_tracking is True
        assert executor.timeout == 300

        # Custom initialization
        executor = DSPyPipelineExecutor(cache_enabled=False, mlflow_tracking=False, timeout=60)
        assert executor.cache_enabled is False
        assert executor.mlflow_tracking is False
        assert executor.timeout == 60

    def test_validate_inputs_success(self):
        """Test successful input validation."""
        inputs = {"input1": "value1", "input2": "value2"}

        # Should not raise any exception
        self.executor._validate_inputs(inputs, self.mock_program)

    def test_validate_inputs_missing_field(self):
        """Test input validation with missing required field."""
        inputs = {"input1": "value1"}  # Missing input2

        with pytest.raises(ValidationError) as exc_info:
            self.executor._validate_inputs(inputs, self.mock_program)

        assert "Missing required input fields" in str(exc_info.value)
        assert "input2" in str(exc_info.value)

    def test_validate_inputs_extra_fields(self):
        """Test input validation with extra fields (should pass)."""
        inputs = {"input1": "value1", "input2": "value2", "extra_field": "extra_value"}

        # Should not raise exception - extra fields are allowed
        self.executor._validate_inputs(inputs, self.mock_program)

    def test_execute_single_success(self):
        """Test successful single execution."""
        inputs = {"input1": "test", "input2": "data"}

        result = self.executor.execute(program=self.mock_program, inputs=inputs)

        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.outputs["output"] == "processed_test"
        assert result.error is None
        assert result.execution_time > 0
        assert result.program_name == "test_program"

    def test_execute_single_failure(self):
        """Test single execution with failure."""
        self.mock_program._should_fail = True
        inputs = {"input1": "test", "input2": "data"}

        result = self.executor.execute(program=self.mock_program, inputs=inputs)

        assert isinstance(result, ExecutionResult)
        assert result.success is False
        assert result.outputs is None
        assert "Mock execution error" in result.error
        assert result.execution_time > 0

    def test_execute_with_model_id(self):
        """Test execution with model ID instead of program instance."""
        with patch.object(self.executor, "_load_program_by_id") as mock_load:
            mock_load.return_value = self.mock_program

            inputs = {"input1": "test", "input2": "data"}
            result = self.executor.execute(model_id="test-model-123", inputs=inputs)

            mock_load.assert_called_once_with("test-model-123")
            assert result.success is True
            assert result.outputs["output"] == "processed_test"

    def test_execute_batch(self):
        """Test batch execution."""
        batch_inputs = [
            {"input1": "test1", "input2": "data1"},
            {"input1": "test2", "input2": "data2"},
            {"input1": "test3", "input2": "data3"},
        ]

        results = self.executor.execute_batch(program=self.mock_program, inputs_list=batch_inputs)

        assert len(results) == 3
        assert all(isinstance(r, ExecutionResult) for r in results)
        assert results[0].outputs["output"] == "processed_test1"
        assert results[1].outputs["output"] == "processed_test2"
        assert results[2].outputs["output"] == "processed_test3"

    def test_execute_batch_with_failures(self):
        """Test batch execution with some failures."""
        batch_inputs = [
            {"input1": "test1", "input2": "data1"},
            {"input1": "test2"},  # Missing required field
            {"input1": "test3", "input2": "data3"},
        ]

        results = self.executor.execute_batch(program=self.mock_program, inputs_list=batch_inputs)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert "Missing required input fields" in results[1].error
        assert results[2].success is True

    def test_dry_run_mode(self):
        """Test dry-run execution mode."""
        inputs = {"input1": "test", "input2": "data"}

        result = self.executor.execute(
            program=self.mock_program, inputs=inputs, mode=ExecutionMode.DRY_RUN
        )

        assert result.success is True
        assert result.outputs is None  # No actual execution
        assert result.metadata["mode"] == "dry_run"
        assert result.metadata["validation_passed"] is True
        assert self.mock_program._call_count == 0  # Program not actually called

    def test_debug_mode(self):
        """Test debug execution mode."""
        inputs = {"input1": "test", "input2": "data"}

        with patch("src.services.dspy_pipeline_executor.logger") as mock_logger:
            result = self.executor.execute(
                program=self.mock_program, inputs=inputs, mode=ExecutionMode.DEBUG
            )

            assert result.success is True
            assert result.metadata["mode"] == "debug"
            assert "debug_trace" in result.metadata
            # Verify debug logging was called
            assert mock_logger.debug.called

    @patch("mlflow.start_run")
    @patch("mlflow.log_params")
    @patch("mlflow.log_metrics")
    @patch("mlflow.set_tags")
    @patch("mlflow.set_experiment")
    @patch("mlflow.set_tracking_uri")
    def test_mlflow_tracking(
        self,
        mock_set_uri,
        mock_set_exp,
        mock_set_tags,
        mock_log_metrics,
        mock_log_params,
        mock_start_run,
    ):
        """Test MLflow tracking integration."""
        # Create executor with MLflow enabled (patched initialization will succeed)
        executor = DSPyPipelineExecutor(mlflow_tracking=True)

        inputs = {"input1": "test", "input2": "data"}

        executor.execute(program=self.mock_program, inputs=inputs)

        # Verify MLflow tracking was initialized
        mock_start_run.assert_called_once()
        mock_log_params.assert_called()
        mock_log_metrics.assert_called()

        # Check logged parameters - first call should have program_name
        assert mock_log_params.call_count >= 1
        first_call_params = mock_log_params.call_args_list[0][0][0]
        assert "program_name" in first_call_params
        assert first_call_params["program_name"] == "test_program"

        # Check logged metrics
        logged_metrics = mock_log_metrics.call_args[0][0]
        assert "execution_time" in logged_metrics
        assert "success" in logged_metrics

    @patch("mlflow.start_run")
    @patch("mlflow.log_params")
    @patch("mlflow.log_metrics")
    @patch("mlflow.set_tags")
    @patch("mlflow.set_experiment")
    @patch("mlflow.set_tracking_uri")
    def test_execute_logs_contributor_tags(
        self,
        mock_set_uri,
        mock_set_exp,
        mock_set_tags,
        mock_log_metrics,
        mock_log_params,
        mock_start_run,
    ):
        """Test contributor attribution tags are logged for each execution."""
        executor = DSPyPipelineExecutor(mlflow_tracking=True)

        inputs = {"input1": "test", "input2": "data"}
        result = executor.execute(
            program=self.mock_program,
            inputs=inputs,
            contributor_id="author-1",
            contributor_role="prompt_author",
            contributors_by_role={
                "training_data_uploader": "uploader-1",
                "human_labeler": "labeler-1",
            },
        )

        assert result.success is True
        assert result.metadata["contributor_attribution"]["primary_contributor_id"] == "author-1"
        assert result.metadata["contributor_attribution"]["contributors_by_role"] == {
            "prompt_author": "author-1",
            "training_data_uploader": "uploader-1",
            "human_labeler": "labeler-1",
        }

        logged_tags = mock_set_tags.call_args[0][0]
        assert logged_tags["contributor_id"] == "author-1"
        assert logged_tags["hokusai.contributor.prompt_author_id"] == "author-1"
        assert logged_tags["hokusai.contributor.training_data_uploader_id"] == "uploader-1"
        assert logged_tags["hokusai.contributor.human_labeler_id"] == "labeler-1"

    def test_program_caching(self):
        """Test program caching functionality."""
        model_id = "test-model-123"

        # Clear cache first to ensure clean test
        self.executor.clear_cache()

        # Mock the model loader instead of the method directly
        with patch.object(self.executor._model_loader, "load_from_config") as mock_load:
            mock_load.return_value = {"program": self.mock_program}

            # Mock the registry at import level
            with patch("src.services.model_registry.HokusaiModelRegistry") as mock_registry_class:
                mock_registry = MagicMock()
                mock_registry.get_model.return_value = {"program_path": "test_path"}
                mock_registry_class.return_value = mock_registry

                # First execution - should load program
                result1 = self.executor.execute(
                    model_id=model_id, inputs={"input1": "test1", "input2": "data1"}
                )

                # Second execution - should use cached program
                result2 = self.executor.execute(
                    model_id=model_id, inputs={"input1": "test2", "input2": "data2"}
                )

                # Model loader should only be called once due to caching
                assert mock_load.call_count == 1
                assert result1.success is True
                assert result2.success is True

    def test_timeout_handling(self):
        """Test execution timeout handling."""
        # Create a program that takes too long
        slow_program = MockDSPyProgram()

        def slow_forward(**kwargs):
            # Simulate slow execution by raising timeout error
            # This tests the timeout handling without actual sleep
            raise TimeoutError("Execution timed out")

        slow_program.forward = slow_forward

        # Set short timeout
        executor = DSPyPipelineExecutor(timeout=0.1)  # 100ms timeout

        result = executor.execute(program=slow_program, inputs={"input1": "test", "input2": "data"})

        assert result.success is False
        assert "timeout" in result.error.lower()

    def test_serialization_handling(self):
        """Test handling of complex output types."""
        # Create program with complex outputs
        complex_program = MockDSPyProgram()

        def complex_forward(**kwargs):
            return {"output": "text", "nested": {"key": "value"}, "list": [1, 2, 3], "number": 42.5}

        complex_program.forward = complex_forward

        result = self.executor.execute(
            program=complex_program, inputs={"input1": "test", "input2": "data"}
        )

        assert result.success is True
        assert result.outputs["nested"]["key"] == "value"
        assert result.outputs["list"] == [1, 2, 3]

        # Ensure outputs are JSON serializable
        json_str = json.dumps(result.outputs)
        assert json_str is not None

    def test_retry_logic(self):
        """Test retry logic for transient failures."""
        # Create a program that fails first time, succeeds second time
        flaky_program = MockDSPyProgram()
        flaky_program._attempts = 0

        def flaky_forward(**kwargs):
            flaky_program._attempts += 1
            if flaky_program._attempts == 1:
                raise Exception("Transient error")
            return {"output": "success"}

        flaky_program.forward = flaky_forward

        executor = DSPyPipelineExecutor(max_retries=2)
        result = executor.execute(
            program=flaky_program, inputs={"input1": "test", "input2": "data"}
        )

        assert result.success is True
        assert result.outputs["output"] == "success"
        assert flaky_program._attempts == 2  # First attempt failed, second succeeded

    def test_get_execution_stats(self):
        """Test execution statistics tracking."""
        # Execute several times
        for i in range(5):
            self.executor.execute(
                program=self.mock_program, inputs={"input1": f"test{i}", "input2": "data"}
            )

        # Make one fail
        self.mock_program._should_fail = True
        self.executor.execute(
            program=self.mock_program, inputs={"input1": "fail", "input2": "data"}
        )

        stats = self.executor.get_execution_stats()

        assert stats["total_executions"] == 6
        assert stats["successful_executions"] == 5
        assert stats["failed_executions"] == 1
        assert stats["success_rate"] == 5 / 6
        assert "average_execution_time" in stats
        assert "p95_execution_time" in stats


class TestExecutionResult:
    """Test cases for ExecutionResult class."""

    def test_to_dict(self):
        """Test ExecutionResult serialization."""
        result = ExecutionResult(
            success=True,
            outputs={"key": "value"},
            error=None,
            execution_time=0.123,
            program_name="test_program",
            metadata={"extra": "data"},
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["outputs"]["key"] == "value"
        assert result_dict["error"] is None
        assert result_dict["execution_time"] == 0.123
        assert result_dict["program_name"] == "test_program"
        assert result_dict["metadata"]["extra"] == "data"

    def test_to_json(self):
        """Test ExecutionResult JSON serialization."""
        result = ExecutionResult(
            success=True,
            outputs={"key": "value", "number": 42},
            error=None,
            execution_time=0.123,
            program_name="test_program",
        )

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["success"] is True
        assert parsed["outputs"]["key"] == "value"
        assert parsed["outputs"]["number"] == 42
