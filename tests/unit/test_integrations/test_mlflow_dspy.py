"""Unit tests for MLflow DSPy integration."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.integrations.mlflow_dspy import (
    MLflowDSPyConfig,
    TracedModule,
    autolog,
    disable_autolog,
    get_autolog_client,
)


class TestMLflowDSPyConfig:
    """Test cases for MLflowDSPyConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MLflowDSPyConfig()

        assert config.enabled is True
        assert config.log_inputs is True
        assert config.log_outputs is True
        assert config.log_signatures is True
        assert config.log_intermediate_steps is True
        assert config.sampling_rate == 1.0
        assert config.trace_buffer_size == 100

    def test_config_from_env(self, monkeypatch):
        """Test configuration from environment variables."""
        monkeypatch.setenv("MLFLOW_DSPY_ENABLED", "false")
        monkeypatch.setenv("MLFLOW_DSPY_LOG_INPUTS", "false")
        monkeypatch.setenv("MLFLOW_DSPY_SAMPLING_RATE", "0.5")
        monkeypatch.setenv("MLFLOW_DSPY_BUFFER_SIZE", "50")

        config = MLflowDSPyConfig.from_env()

        assert config.enabled is False
        assert config.log_inputs is False
        assert config.sampling_rate == 0.5
        assert config.trace_buffer_size == 50

    def test_config_validation(self):
        """Test configuration validation."""
        # Valid config
        config = MLflowDSPyConfig(sampling_rate=0.5)
        assert config.sampling_rate == 0.5

        # Invalid sampling rate
        with pytest.raises(ValueError, match="Sampling rate must be between 0 and 1"):
            MLflowDSPyConfig(sampling_rate=1.5)

        # Invalid buffer size
        with pytest.raises(ValueError, match="Buffer size must be positive"):
            MLflowDSPyConfig(trace_buffer_size=0)


class TestAutolog:
    """Test cases for autolog functionality."""

    def test_autolog_initialization(self):
        """Test autolog initialization."""
        with patch("mlflow.set_experiment") as mock_set_experiment:
            with patch("src.integrations.mlflow_dspy.DSPY_AVAILABLE", False):
                client = autolog()

                assert client is not None
                assert client.config.enabled is True
                mock_set_experiment.assert_called_once()

    def test_autolog_with_config(self):
        """Test autolog with custom configuration."""
        config = MLflowDSPyConfig(log_inputs=False, sampling_rate=0.5)

        with patch("src.integrations.mlflow_dspy.DSPY_AVAILABLE", False):
            client = autolog(config=config)

            assert client.config.log_inputs is False
            assert client.config.sampling_rate == 0.5

    def test_autolog_disabled(self, monkeypatch):
        """Test autolog when disabled via environment."""
        monkeypatch.setenv("MLFLOW_DSPY_ENABLED", "false")

        # Clear any existing client
        import src.integrations.mlflow_dspy

        src.integrations.mlflow_dspy._autolog_client = None

        with patch("src.integrations.mlflow_dspy.DSPY_AVAILABLE", False):
            client = autolog()

            assert client.config.enabled is False

    def test_autolog_singleton(self):
        """Test that autolog returns the same client instance."""
        with patch("src.integrations.mlflow_dspy.DSPY_AVAILABLE", False):
            client1 = autolog()
            client2 = autolog()

            assert client1 is client2

    def test_disable_autolog(self):
        """Test disabling autolog."""
        with patch("src.integrations.mlflow_dspy.DSPY_AVAILABLE", False):
            client = autolog()
            assert client.config.enabled is True

            disable_autolog()

            # Get client again - should be disabled
            client = get_autolog_client()
            assert client.config.enabled is False


class TestTracedModule:
    """Test cases for TracedModule wrapper."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a mock DSPy module
        self.mock_module = Mock()
        self.mock_module.__class__.__name__ = "TestModule"
        self.mock_module.forward = Mock(return_value={"output": "test"})

        # Create mock signature
        self.mock_signature = Mock()
        self.mock_signature.input_fields = [
            Mock(name="input1", type=str),
            Mock(name="input2", type=int),
        ]
        self.mock_signature.output_fields = [Mock(name="output", type=str)]
        self.mock_module.signature = self.mock_signature

    def test_traced_module_creation(self):
        """Test creating a traced module."""
        traced = TracedModule(self.mock_module)

        assert traced.module == self.mock_module
        assert traced.module_name == "TestModule"

    def test_traced_module_execution(self):
        """Test executing a traced module."""
        traced = TracedModule(self.mock_module)

        with patch("mlflow.start_span") as mock_start_span:
            mock_span = MagicMock()
            mock_start_span.return_value.__enter__.return_value = mock_span

            result = traced.forward(input1="test", input2=42)

            assert result == {"output": "test"}
            mock_start_span.assert_called_once_with(name="TestModule")

            # Check that inputs were logged
            mock_span.set_inputs.assert_called_once()
            inputs = mock_span.set_inputs.call_args[0][0]
            assert inputs["input1"] == "test"
            assert inputs["input2"] == 42

            # Check that outputs were logged
            mock_span.set_outputs.assert_called_once_with({"output": "test"})

    def test_traced_module_with_error(self):
        """Test traced module handling errors."""
        self.mock_module.forward.side_effect = ValueError("Test error")
        traced = TracedModule(self.mock_module)

        with patch("mlflow.start_span") as mock_start_span:
            mock_span = MagicMock()
            mock_start_span.return_value.__enter__.return_value = mock_span

            with pytest.raises(ValueError, match="Test error"):
                traced.forward(input1="test")

            # Check that error was logged
            mock_span.set_attributes.assert_called()
            attrs = mock_span.set_attributes.call_args[0][0]
            assert attrs["status"] == "error"

    def test_traced_module_sampling(self):
        """Test traced module with sampling."""
        config = MLflowDSPyConfig(sampling_rate=0.0)  # Never sample
        traced = TracedModule(self.mock_module, config=config)

        with patch("mlflow.start_span") as mock_start_span:
            result = traced.forward(input1="test")

            # Should not create span due to sampling
            mock_start_span.assert_not_called()
            assert result == {"output": "test"}

    def test_traced_module_signature_logging(self):
        """Test logging signature information."""
        traced = TracedModule(self.mock_module)

        with patch("mlflow.start_span") as mock_start_span:
            mock_span = MagicMock()
            mock_start_span.return_value.__enter__.return_value = mock_span

            traced.forward(input1="test", input2=42)

            # Check that signature was logged in attributes
            mock_span.set_attributes.assert_called()
            attributes = mock_span.set_attributes.call_args[0][0]
            assert "signature.input_fields" in attributes
            assert "signature.output_fields" in attributes

    def test_traced_module_nested_execution(self):
        """Test nested module execution."""
        # Create nested module
        nested_module = Mock()
        nested_module.__class__.__name__ = "NestedModule"
        nested_module.forward = Mock(return_value={"nested": "result"})

        # Make main module call nested module
        def forward_with_nested(*args, **kwargs):
            nested_result = TracedModule(nested_module).forward()
            return {"output": "test", "nested": nested_result}

        self.mock_module.forward = forward_with_nested
        traced = TracedModule(self.mock_module)

        with patch("mlflow.start_span") as mock_start_span:
            spans = []

            def create_span(name):
                span = MagicMock()
                span.name = name
                spans.append(span)
                return span

            mock_start_span.side_effect = lambda name: MagicMock(
                __enter__=lambda self: create_span(name), __exit__=lambda self, *args: None
            )

            traced.forward(input1="test")

            # Should create spans for both modules
            assert len(spans) == 2
            assert any(s.name == "TestModule" for s in spans)
            assert any(s.name == "NestedModule" for s in spans)


class TestMLflowDSPyIntegration:
    """Integration tests for MLflow DSPy functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a mock DSPy module for integration tests
        self.mock_module = Mock()
        self.mock_module.__class__.__name__ = "TestModule"
        self.mock_module.forward = Mock(return_value={"output": "test"})

    @pytest.fixture
    def mock_dspy(self):
        """Create a mock DSPy module."""
        with patch("src.integrations.mlflow_dspy.dspy") as mock:
            yield mock

    def test_auto_wrap_dspy_modules(self, mock_dspy):
        """Test automatic wrapping of DSPy modules."""
        # Create mock DSPy module classes
        mock_predict = Mock()
        mock_chain = Mock()
        mock_dspy.Predict = mock_predict
        mock_dspy.ChainOfThought = mock_chain

        # Enable autolog
        autolog()

        # Verify that DSPy module classes were wrapped
        assert hasattr(mock_predict, "_mlflow_wrapped")
        assert hasattr(mock_chain, "_mlflow_wrapped")

    def test_trace_buffering(self):
        """Test trace buffering functionality."""
        config = MLflowDSPyConfig(trace_buffer_size=2)
        autolog(config=config)

        # Create traced modules
        module1 = Mock()
        module1.__class__.__name__ = "Module1"
        module1.forward = Mock(return_value={"result": 1})

        module2 = Mock()
        module2.__class__.__name__ = "Module2"
        module2.forward = Mock(return_value={"result": 2})

        with patch("mlflow.MlflowClient") as mock_client:
            traced1 = TracedModule(module1, config=config)
            traced2 = TracedModule(module2, config=config)

            # Execute modules
            traced1.forward()
            traced2.forward()

            # Buffer should flush after 2 traces
            assert mock_client.return_value.log_batch.called

    def test_custom_metadata(self):
        """Test adding custom metadata to traces."""
        traced = TracedModule(self.mock_module)

        with patch("mlflow.start_span") as mock_start_span:
            mock_span = MagicMock()
            mock_start_span.return_value.__enter__.return_value = mock_span

            # Add custom metadata
            traced.set_metadata({"custom_key": "custom_value"})
            traced.forward(input1="test")

            # Check that custom metadata was logged
            mock_span.set_attributes.assert_called()
            attributes = mock_span.set_attributes.call_args[0][0]
            assert attributes.get("custom_key") == "custom_value"
