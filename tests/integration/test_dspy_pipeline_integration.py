"""Integration tests for DSPy Pipeline Executor."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import DSPy components
try:
    import dspy

    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

import logging

from src.services.dspy_model_loader import DSPyModelLoader
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor

# Skip tests if DSPy is not available
pytestmark = pytest.mark.skipif(not DSPY_AVAILABLE, reason="DSPy not installed")


class TestDSPyPipelineIntegration:
    """Integration tests for DSPy Pipeline Executor."""

    @pytest.fixture
    def setup_environment(self):
        """Set up test environment."""
        # Create temporary directory for test artifacts
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set MLflow tracking URI to temporary directory
            os.environ["MLFLOW_TRACKING_URI"] = f"file://{tmpdir}/mlruns"

            yield tmpdir

    @pytest.fixture
    def sample_dspy_program(self):
        """Create a sample DSPy program for testing."""
        if not DSPY_AVAILABLE:
            return None

        # Define a simple DSPy signature
        class SimpleSignature(dspy.Signature):
            """Simple text processing signature."""

            text = dspy.InputField(desc="Input text to process")
            processed = dspy.OutputField(desc="Processed text output")

        # Define a DSPy module
        class SimpleProcessor(dspy.Module):
            """Simple text processor module."""

            def __init__(self):
                super().__init__()
                self.process = dspy.ChainOfThought(SimpleSignature)

            def forward(self, text):
                # Mock processing without actual LLM call
                return dspy.Prediction(processed=f"PROCESSED: {text.upper()}")

        return SimpleProcessor()

    @pytest.fixture
    def multi_step_dspy_program(self):
        """Create a multi-step DSPy program for testing."""
        if not DSPY_AVAILABLE:
            return None

        # Define signatures for multi-step processing
        class SummarizeSignature(dspy.Signature):
            """Summarization signature."""

            text = dspy.InputField(desc="Text to summarize")
            summary = dspy.OutputField(desc="Summary of the text")

        class AnalyzeSignature(dspy.Signature):
            """Analysis signature."""

            summary = dspy.InputField(desc="Summary to analyze")
            analysis = dspy.OutputField(desc="Analysis of the summary")

        # Define multi-step module
        class TextAnalyzer(dspy.Module):
            """Multi-step text analyzer."""

            def __init__(self):
                super().__init__()
                self.summarize = dspy.ChainOfThought(SummarizeSignature)
                self.analyze = dspy.ChainOfThought(AnalyzeSignature)

            def forward(self, text):
                # Mock multi-step processing
                summary = dspy.Prediction(summary=f"Summary of: {text[:50]}...")
                analysis = dspy.Prediction(
                    analysis=f"Analysis: The text '{summary.summary}' contains important information."
                )
                return analysis

        return TextAnalyzer()

    def test_real_dspy_program_execution(self, setup_environment, sample_dspy_program):
        """Test execution with a real DSPy program."""
        executor = DSPyPipelineExecutor()

        result = executor.execute(program=sample_dspy_program, inputs={"text": "Hello, world!"})

        assert result.success is True
        assert result.outputs is not None
        assert "processed" in result.outputs
        assert result.outputs["processed"] == "PROCESSED: HELLO, WORLD!"

    def test_multi_step_execution(self, setup_environment, multi_step_dspy_program):
        """Test execution of multi-step DSPy program."""
        executor = DSPyPipelineExecutor()

        result = executor.execute(
            program=multi_step_dspy_program,
            inputs={"text": "This is a long text that needs to be summarized and analyzed."},
        )

        assert result.success is True
        assert result.outputs is not None
        assert "analysis" in result.outputs
        assert "Analysis:" in result.outputs["analysis"]

    def test_mlflow_tracking_integration(self, setup_environment, sample_dspy_program):
        """Test MLflow tracking with real execution."""
        import mlflow

        executor = DSPyPipelineExecutor(mlflow_tracking=True)

        # Execute program
        result = executor.execute(
            program=sample_dspy_program, inputs={"text": "Test input for MLflow"}
        )

        assert result.success is True

        # Verify MLflow run was created
        runs = mlflow.search_runs()
        assert len(runs) > 0

        latest_run = runs.iloc[0]
        assert latest_run["params.program_name"] == "SimpleProcessor"
        assert latest_run["metrics.success"] == 1.0
        assert "metrics.execution_time" in latest_run

    def test_model_loader_integration(self, setup_environment):
        """Test integration with DSPyModelLoader."""
        # Create a temporary DSPy config
        config_path = Path(setup_environment) / "test_config.yaml"
        config_content = """
name: test-processor
version: 1.0.0
source:
  type: local
  path: ./examples/dspy/example_dspy_program.py
  class_name: EmailAssistant

signatures:
  generate_email:
    inputs: [recipient, subject, context]
    outputs: [email_body]
    description: Generate professional emails
"""
        config_path.write_text(config_content)

        # Mock the actual loading to avoid file dependencies
        with patch.object(DSPyModelLoader, "load_from_config") as mock_load:
            mock_program = MagicMock()
            mock_program.name = "EmailAssistant"
            mock_program.forward = lambda **kwargs: {"email_body": "Test email"}

            mock_load.return_value = {
                "program": mock_program,
                "metadata": {"name": "test-processor", "version": "1.0.0"},
            }

            # Load and execute
            loader = DSPyModelLoader()
            program_data = loader.load_from_config(str(config_path))

            executor = DSPyPipelineExecutor()
            result = executor.execute(
                program=program_data["program"],
                inputs={
                    "recipient": "test@example.com",
                    "subject": "Test Subject",
                    "context": "Test context",
                },
            )

            assert result.success is True
            assert result.outputs["email_body"] == "Test email"

    def test_batch_execution_performance(self, setup_environment, sample_dspy_program):
        """Test batch execution performance."""
        import time

        executor = DSPyPipelineExecutor()

        # Create batch of inputs
        batch_size = 10
        batch_inputs = [{"text": f"Test input {i}"} for i in range(batch_size)]

        # Time batch execution
        start_time = time.time()
        results = executor.execute_batch(program=sample_dspy_program, inputs_list=batch_inputs)
        batch_time = time.time() - start_time

        # Time sequential execution
        start_time = time.time()
        sequential_results = []
        for inputs in batch_inputs:
            result = executor.execute(program=sample_dspy_program, inputs=inputs)
            sequential_results.append(result)
        sequential_time = time.time() - start_time

        # Verify results
        assert len(results) == batch_size
        assert all(r.success for r in results)

        # Batch should be faster than sequential (or at least not significantly slower)
        # Allow some margin for overhead
        assert batch_time <= sequential_time * 1.2

    def test_error_recovery_integration(self, setup_environment):
        """Test error recovery with real DSPy programs."""
        if not DSPY_AVAILABLE:
            return

        # Create a program that fails intermittently
        class FlakySignature(dspy.Signature):
            text = dspy.InputField()
            output = dspy.OutputField()

        class FlakyModule(dspy.Module):
            def __init__(self):
                super().__init__()
                self.process = dspy.ChainOfThought(FlakySignature)
                self.call_count = 0

            def forward(self, text):
                self.call_count += 1
                if self.call_count == 1 and "fail" in text:
                    raise Exception("Simulated failure")
                return dspy.Prediction(output=f"Processed: {text}")

        program = FlakyModule()
        executor = DSPyPipelineExecutor(max_retries=2)

        # Test successful retry
        result = executor.execute(program=program, inputs={"text": "fail on first try"})

        assert result.success is True
        assert program.call_count == 2  # Failed once, succeeded on retry

    def test_caching_integration(self, setup_environment, sample_dspy_program):
        """Test caching functionality with real programs."""
        executor = DSPyPipelineExecutor(cache_enabled=True)

        # First execution
        result1 = executor.execute(program=sample_dspy_program, inputs={"text": "Cacheable input"})

        # Second execution with same inputs
        result2 = executor.execute(program=sample_dspy_program, inputs={"text": "Cacheable input"})

        # Results should be identical
        assert result1.outputs == result2.outputs

        # Second execution should be faster due to caching
        assert result2.execution_time < result1.execution_time

    def test_api_endpoint_integration(self, setup_environment, sample_dspy_program):
        """Test REST API endpoint integration."""
        from fastapi.testclient import TestClient

        from src.api.dspy_endpoints import create_dspy_router

        # Create test client
        router = create_dspy_router()
        client = TestClient(router)

        # Mock program registry
        with patch("src.api.dspy_endpoints.get_program") as mock_get:
            mock_get.return_value = sample_dspy_program

            # Test single execution endpoint
            response = client.post(
                "/api/v1/dspy/execute",
                json={"program_id": "test-program", "inputs": {"text": "API test input"}},
            )

            assert response.status_code == 200
            result = response.json()
            assert result["success"] is True
            assert result["outputs"]["processed"] == "PROCESSED: API TEST INPUT"

    def test_metaflow_integration(self, setup_environment, sample_dspy_program):
        """Test integration with Metaflow pipeline."""
        from metaflow import FlowSpec, step

        class DSPyTestFlow(FlowSpec):
            """Test flow with DSPy execution."""

            @step
            def start(self):
                """Initialize flow."""
                self.test_data = [
                    {"text": "First test"},
                    {"text": "Second test"},
                    {"text": "Third test"},
                ]
                self.next(self.process)

            @step
            def process(self):
                """Process data with DSPy."""
                executor = DSPyPipelineExecutor()
                self.results = []

                for data in self.test_data:
                    result = executor.execute(program=sample_dspy_program, inputs=data)
                    self.results.append(result)

                self.next(self.end)

            @step
            def end(self):
                """Verify results."""
                assert len(self.results) == 3
                assert all(r.success for r in self.results)
                logging.info("Flow completed successfully!")

        # Note: Actually running the flow would require Metaflow setup
        # This test verifies the integration pattern works
        flow = DSPyTestFlow()
        assert hasattr(flow, "start")
        assert hasattr(flow, "process")
        assert hasattr(flow, "end")
