"""Unit tests for MLflow DSPy integration."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import os
import json
import time
import threading
from typing import Dict, Any

from src.integrations.mlflow_dspy import (
    MLflowDSPyConfig,
    TracedModule,
    MLflowDSPyClient,
    autolog,
    get_autolog_client,
    disable_autolog,
    DSPY_AVAILABLE
)


class TestMLflowDSPyConfig:
    """Test suite for MLflowDSPyConfig class."""

    def test_config_defaults(self):
        """Test default configuration values."""
        config = MLflowDSPyConfig()

        assert config.enabled is True
        assert config.log_inputs is True
        assert config.log_outputs is True
        assert config.log_signatures is True
        assert config.log_intermediate_steps is True
        assert config.sampling_rate == 1.0
        assert config.trace_buffer_size == 100
        assert config.experiment_name == "dspy-traces"
        assert config.custom_tags == {}

    def test_config_custom_values(self):
        """Test custom configuration values."""
        custom_tags = {"team": "ml", "project": "hokusai"}
        config = MLflowDSPyConfig(
            enabled=False,
            log_inputs=False,
            sampling_rate=0.5,
            trace_buffer_size=50,
            experiment_name="custom-experiment",
            custom_tags=custom_tags
        )

        assert config.enabled is False
        assert config.log_inputs is False
        assert config.sampling_rate == 0.5
        assert config.trace_buffer_size == 50
        assert config.experiment_name == "custom-experiment"
        assert config.custom_tags == custom_tags

    def test_config_validation(self):
        """Test configuration validation."""
        # Invalid sampling rate
        with pytest.raises(ValueError, match="Sampling rate must be between 0 and 1"):
            MLflowDSPyConfig(sampling_rate=1.5)

        with pytest.raises(ValueError, match="Sampling rate must be between 0 and 1"):
            MLflowDSPyConfig(sampling_rate=-0.1)

        # Invalid buffer size
        with pytest.raises(ValueError, match="Buffer size must be positive"):
            MLflowDSPyConfig(trace_buffer_size=0)

    @patch.dict(os.environ, {
        "MLFLOW_DSPY_ENABLED": "false",
        "MLFLOW_DSPY_LOG_INPUTS": "false",
        "MLFLOW_DSPY_SAMPLING_RATE": "0.8",
        "MLFLOW_DSPY_BUFFER_SIZE": "200",
        "MLFLOW_DSPY_EXPERIMENT": "env-experiment"
    })
    def test_config_from_env(self):
        """Test creating configuration from environment variables."""
        config = MLflowDSPyConfig.from_env()

        assert config.enabled is False
        assert config.log_inputs is False
        assert config.sampling_rate == 0.8
        assert config.trace_buffer_size == 200
        assert config.experiment_name == "env-experiment"


class TestTracedModule:
    """Test suite for TracedModule wrapper."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock DSPy module
        self.mock_module = Mock()
        self.mock_module.__class__.__name__ = "TestModule"
        self.mock_module.forward = Mock(return_value={"output": "test"})

        # Create traced module
        self.config = MLflowDSPyConfig(enabled=True)
        self.traced_module = TracedModule(self.mock_module, self.config)

    def test_traced_module_initialization(self):
        """Test traced module initialization."""
        assert self.traced_module.module == self.mock_module
        assert self.traced_module.config == self.config
        assert self.traced_module.module_name == "TestModule"
        assert self.traced_module._metadata == {}

    def test_set_metadata(self):
        """Test setting custom metadata."""
        metadata = {"user_id": "123", "session": "abc"}
        self.traced_module.set_metadata(metadata)

        assert self.traced_module._metadata == metadata

        # Test updating metadata
        self.traced_module.set_metadata({"extra": "value"})
        assert self.traced_module._metadata == {
            "user_id": "123",
            "session": "abc",
            "extra": "value"
        }

    @patch("mlflow.start_span")
    def test_forward_with_tracing_enabled(self, mock_start_span):
        """Test forward execution with tracing enabled."""
        # Mock span
        mock_span = MagicMock()
        mock_start_span.return_value.__enter__.return_value = mock_span

        # Execute forward
        result = self.traced_module.forward("input1", key="value")

        assert result == {"output": "test"}
        mock_start_span.assert_called_once_with(name="TestModule")
        mock_span.set_inputs.assert_called_once()
        mock_span.set_outputs.assert_called_once()
        self.mock_module.forward.assert_called_once_with("input1", key="value")

    def test_forward_with_tracing_disabled(self):
        """Test forward execution with tracing disabled."""
        self.traced_module.config.enabled = False

        result = self.traced_module.forward("input1")

        assert result == {"output": "test"}
        self.mock_module.forward.assert_called_once_with("input1")

    @patch("random.random")
    def test_forward_with_sampling(self, mock_random):
        """Test forward execution with sampling."""
        self.traced_module.config.sampling_rate = 0.5

        # Should skip tracing (random > sampling_rate)
        mock_random.return_value = 0.7
        result = self.traced_module.forward("input1")

        assert result == {"output": "test"}
        self.mock_module.forward.assert_called_once_with("input1")

    @patch("mlflow.start_span")
    def test_forward_with_signature_logging(self, mock_start_span):
        """Test forward with signature logging."""
        # Add signature to mock module
        self.mock_module.signature = Mock()
        self.mock_module.signature.input_fields = ["field1", "field2"]
        self.mock_module.signature.output_fields = ["output"]

        mock_span = MagicMock()
        mock_start_span.return_value.__enter__.return_value = mock_span

        result = self.traced_module.forward("input1")

        # Should log signature attributes
        mock_span.set_attributes.assert_called()

    @patch("mlflow.start_span")
    def test_forward_with_error(self, mock_start_span):
        """Test forward execution with error."""
        mock_span = MagicMock()
        mock_start_span.return_value.__enter__.return_value = mock_span

        # Make forward raise an error
        self.mock_module.forward.side_effect = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            self.traced_module.forward("input1")

        # Should still log the error
        mock_span.set_status.assert_called_once()

    def test_attribute_copying(self):
        """Test that attributes are copied from original module."""
        # Add some attributes to mock module
        self.mock_module.custom_attr = "value"
        self.mock_module.method = Mock()

        # Create new traced module
        traced = TracedModule(self.mock_module, self.config)

        assert hasattr(traced, "custom_attr")
        assert traced.custom_attr == "value"


class TestMLflowDSPyClient:
    """Test suite for MLflowDSPyClient class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = MLflowDSPyConfig()
        self.client = MLflowDSPyClient(self.config)

    def test_client_initialization(self):
        """Test client initialization."""
        assert self.client.config == self.config
        assert self.client._traces == []
        assert self.client._lock is not None
        assert self.client._active is True

    def test_add_trace(self):
        """Test adding traces."""
        trace_data = {
            "module": "TestModule",
            "inputs": {"x": 1},
            "outputs": {"y": 2},
            "timestamp": time.time()
        }

        self.client.add_trace(trace_data)

        assert len(self.client._traces) == 1
        assert self.client._traces[0] == trace_data

    def test_add_trace_buffer_flush(self):
        """Test automatic buffer flush."""
        self.client.config.trace_buffer_size = 2
        self.client.flush = Mock()

        # Add traces up to buffer size
        self.client.add_trace({"trace": 1})
        self.client.add_trace({"trace": 2})

        # Should trigger flush
        self.client.flush.assert_called_once()

    def test_get_traces(self):
        """Test getting traces."""
        traces = [{"trace": i} for i in range(3)]
        for trace in traces:
            self.client.add_trace(trace)

        retrieved = self.client.get_traces()
        assert retrieved == traces

    def test_clear_traces(self):
        """Test clearing traces."""
        self.client.add_trace({"trace": 1})
        self.client.add_trace({"trace": 2})

        self.client.clear()

        assert len(self.client._traces) == 0

    @patch("mlflow.log_dict")
    @patch("mlflow.start_run")
    def test_flush_traces(self, mock_start_run, mock_log_dict):
        """Test flushing traces to MLflow."""
        # Add some traces
        traces = [{"trace": i} for i in range(3)]
        for trace in traces:
            self.client.add_trace(trace)

        # Flush
        self.client.flush()

        # Should start run and log traces
        mock_start_run.assert_called_once()
        assert mock_log_dict.call_count == 3

        # Traces should be cleared
        assert len(self.client._traces) == 0

    def test_shutdown(self):
        """Test client shutdown."""
        self.client.flush = Mock()

        self.client.shutdown()

        assert self.client._active is False
        self.client.flush.assert_called_once()

    def test_wrap_module(self):
        """Test wrapping a DSPy module."""
        mock_module = Mock()
        mock_module.__class__.__name__ = "TestModule"

        wrapped = self.client.wrap_module(mock_module)

        assert isinstance(wrapped, TracedModule)
        assert wrapped.module == mock_module
        assert wrapped.config == self.config


@patch("src.integrations.mlflow_dspy.DSPY_AVAILABLE", True)
class TestAutologFunctions:
    """Test suite for autolog functions."""

    @patch("src.integrations.mlflow_dspy._autolog_client", None)
    def test_autolog_initialization(self):
        """Test autolog initialization."""
        config = MLflowDSPyConfig(enabled=True)

        autolog(config)

        from src.integrations.mlflow_dspy import _autolog_client
        assert _autolog_client is not None
        assert _autolog_client.config == config

    def test_get_autolog_client(self):
        """Test getting autolog client."""
        # First, client should be None
        from src.integrations import mlflow_dspy
        mlflow_dspy._autolog_client = None

        client = get_autolog_client()
        assert client is None

        # After autolog, should return client
        autolog(MLflowDSPyConfig())
        client = get_autolog_client()
        assert client is not None

    def test_disable_autolog(self):
        """Test disabling autolog."""
        # First enable autolog
        autolog(MLflowDSPyConfig())

        from src.integrations import mlflow_dspy
        assert mlflow_dspy._autolog_client is not None

        # Now disable
        disable_autolog()
        assert mlflow_dspy._autolog_client is None

    def test_autolog_with_dspy_unavailable(self):
        """Test autolog when DSPy is not available."""
        with patch("src.integrations.mlflow_dspy.DSPY_AVAILABLE", False):
            # Should not raise but won't create client
            autolog(MLflowDSPyConfig())

            from src.integrations import mlflow_dspy
            # Client might still be created but won't work without DSPy


class TestSerializationMethods:
    """Test suite for serialization methods in TracedModule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_module = Mock()
        self.mock_module.__class__.__name__ = "TestModule"
        self.traced_module = TracedModule(self.mock_module)

    def test_serialize_inputs(self):
        """Test input serialization."""
        # Test with various input types
        args = (1, "text", [1, 2, 3])
        kwargs = {"key": "value", "number": 42}

        serialized = self.traced_module._serialize_inputs(args, kwargs)

        assert "args" in serialized
        assert "kwargs" in serialized
        assert serialized["args"] == list(args)
        assert serialized["kwargs"] == kwargs

    def test_serialize_outputs(self):
        """Test output serialization."""
        # Test with dict output
        output = {"result": "value", "score": 0.95}
        serialized = self.traced_module._serialize_outputs(output)
        assert serialized == output

        # Test with list output
        output = [1, 2, 3]
        serialized = self.traced_module._serialize_outputs(output)
        assert serialized == output

        # Test with custom object
        class CustomOutput:
            def __init__(self):
                self.value = 42

        output = CustomOutput()
        serialized = self.traced_module._serialize_outputs(output)
        assert "type" in serialized
        assert serialized["type"] == "CustomOutput"

    def test_extract_signature_info(self):
        """Test signature information extraction."""
        # Mock signature
        self.mock_module.signature = Mock()
        self.mock_module.signature.__class__.__name__ = "TestSignature"
        self.mock_module.signature.input_fields = ["input1", "input2"]
        self.mock_module.signature.output_fields = ["output"]

        sig_info = self.traced_module._extract_signature_info()

        assert sig_info["signature_type"] == "TestSignature"
        assert sig_info["input_fields"] == "input1,input2"
        assert sig_info["output_fields"] == "output"
        assert sig_info["num_input_fields"] == 2
        assert sig_info["num_output_fields"] == 1
