"""MLflow integration for automatic DSPy program tracing.

This module provides automatic MLflow tracing for DSPy programs, capturing
inputs, outputs, and intermediate steps without requiring manual instrumentation.
"""

import os
import random
import threading
import time
from datetime import datetime
from typing import Any, Optional

import mlflow

try:
    import dspy

    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

# Global autolog client instance
_autolog_client: Optional["MLflowDSPyClient"] = None
_client_lock = threading.Lock()


class MLflowDSPyConfig:
    """Configuration for MLflow DSPy autolog functionality."""

    def __init__(
        self,
        enabled: bool = True,
        log_inputs: bool = True,
        log_outputs: bool = True,
        log_signatures: bool = True,
        log_intermediate_steps: bool = True,
        sampling_rate: float = 1.0,
        trace_buffer_size: int = 100,
        experiment_name: str = "dspy-traces",
        custom_tags: Optional[dict[str, str]] = None,
    ) -> None:
        """Initialize MLflow DSPy configuration.

        Args:
            enabled: Whether to enable tracing
            log_inputs: Whether to log input parameters
            log_outputs: Whether to log output values
            log_signatures: Whether to log signature information
            log_intermediate_steps: Whether to log intermediate computation steps
            sampling_rate: Fraction of executions to trace (0.0 to 1.0)
            trace_buffer_size: Number of traces to buffer before flushing
            experiment_name: MLflow experiment name for traces
            custom_tags: Custom tags to add to all traces

        """
        self.enabled = enabled
        self.log_inputs = log_inputs
        self.log_outputs = log_outputs
        self.log_signatures = log_signatures
        self.log_intermediate_steps = log_intermediate_steps
        self.sampling_rate = sampling_rate
        self.trace_buffer_size = trace_buffer_size
        self.experiment_name = experiment_name
        self.custom_tags = custom_tags or {}

        # Validate configuration
        if not 0.0 <= self.sampling_rate <= 1.0:
            raise ValueError("Sampling rate must be between 0 and 1")
        if self.trace_buffer_size < 1:
            raise ValueError("Buffer size must be positive")

    @classmethod
    def from_env(cls) -> "MLflowDSPyConfig":
        """Create configuration from environment variables."""
        return cls(
            enabled=os.getenv("MLFLOW_DSPY_ENABLED", "true").lower() == "true",
            log_inputs=os.getenv("MLFLOW_DSPY_LOG_INPUTS", "true").lower() == "true",
            log_outputs=os.getenv("MLFLOW_DSPY_LOG_OUTPUTS", "true").lower() == "true",
            log_signatures=os.getenv("MLFLOW_DSPY_LOG_SIGNATURES", "true").lower() == "true",
            log_intermediate_steps=os.getenv("MLFLOW_DSPY_LOG_INTERMEDIATE", "true").lower()
            == "true",
            sampling_rate=float(os.getenv("MLFLOW_DSPY_SAMPLING_RATE", "1.0")),
            trace_buffer_size=int(os.getenv("MLFLOW_DSPY_BUFFER_SIZE", "100")),
            experiment_name=os.getenv("MLFLOW_DSPY_EXPERIMENT", "dspy-traces"),
        )


class TracedModule:
    """Wrapper class that adds MLflow tracing to DSPy modules."""

    def __init__(self, module: Any, config: Optional[MLflowDSPyConfig] = None) -> None:
        """Initialize traced module wrapper.

        Args:
            module: The DSPy module to wrap
            config: Tracing configuration

        """
        self.module = module
        self.config = config or MLflowDSPyConfig()
        self.module_name = module.__class__.__name__
        self._metadata: dict[str, Any] = {}

        # Copy all attributes from the original module
        for attr in dir(module):
            if not attr.startswith("_") and attr != "forward":
                try:
                    setattr(self, attr, getattr(module, attr))
                except AttributeError:
                    pass

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        """Set custom metadata to be logged with traces."""
        self._metadata.update(metadata)

    def forward(self, *args, **kwargs) -> Any:
        """Execute the module with tracing."""
        # Check if tracing is enabled and sampling
        if not self.config.enabled or random.random() > self.config.sampling_rate:
            return self.module.forward(*args, **kwargs)

        # Create span for this module execution
        with mlflow.start_span(name=self.module_name) as span:
            try:
                # Log inputs
                if self.config.log_inputs:
                    inputs = self._serialize_inputs(args, kwargs)
                    span.set_inputs(inputs)

                # Log signature information
                if self.config.log_signatures and hasattr(self.module, "signature"):
                    sig_info = self._extract_signature_info()
                    span.set_attributes(sig_info)

                # Add custom metadata
                if self._metadata:
                    span.set_attributes(self._metadata)

                # Execute the module
                start_time = time.time()
                result = self.module.forward(*args, **kwargs)
                execution_time = time.time() - start_time

                # Log outputs
                if self.config.log_outputs:
                    outputs = self._serialize_outputs(result)
                    span.set_outputs(outputs)

                # Log execution metrics
                span.set_attributes(
                    {
                        "execution_time_ms": execution_time * 1000,
                        "module_type": self.module_name,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                # Log success
                span.set_attributes({"status": "success"})

                return result

            except Exception as e:
                # Log error information
                span.set_attributes(
                    {"status": "error", "error_type": type(e).__name__, "error_message": str(e)}
                )
                raise

    def _serialize_inputs(self, args: tuple, kwargs: dict) -> dict[str, Any]:
        """Serialize input arguments for logging."""
        inputs = {}

        # Handle positional arguments
        if args:
            inputs["args"] = [self._safe_serialize(arg) for arg in args]

        # Handle keyword arguments
        inputs.update({k: self._safe_serialize(v) for k, v in kwargs.items()})

        return inputs

    def _serialize_outputs(self, result: Any) -> dict[str, Any]:
        """Serialize output values for logging."""
        if isinstance(result, dict):
            return {k: self._safe_serialize(v) for k, v in result.items()}
        else:
            return {"result": self._safe_serialize(result)}

    def _safe_serialize(self, value: Any) -> Any:
        """Safely serialize a value for logging."""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        elif isinstance(value, (list, tuple)):
            return [self._safe_serialize(v) for v in value[:10]]  # Limit to 10 items
        elif isinstance(value, dict):
            return {k: self._safe_serialize(v) for k, v in list(value.items())[:10]}
        else:
            return str(type(value))

    def _extract_signature_info(self) -> dict[str, Any]:
        """Extract signature information from the module."""
        sig_info = {}

        try:
            if hasattr(self.module, "signature"):
                signature = self.module.signature

                # Extract input fields
                if hasattr(signature, "input_fields"):
                    sig_info["signature.input_fields"] = [
                        f"{field.name}:{field.type.__name__}" for field in signature.input_fields
                    ]

                # Extract output fields
                if hasattr(signature, "output_fields"):
                    sig_info["signature.output_fields"] = [
                        f"{field.name}:{field.type.__name__}" for field in signature.output_fields
                    ]
        except Exception:
            pass

        return sig_info

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to the wrapped module."""
        return getattr(self.module, name)


class MLflowDSPyClient:
    """Client for managing MLflow DSPy autolog functionality."""

    def __init__(self, config: MLflowDSPyConfig) -> None:
        """Initialize the MLflow DSPy client."""
        self.config = config
        self._trace_buffer: list[dict[str, Any]] = []
        self._buffer_lock = threading.Lock()

        if config.enabled:
            # Set up MLflow experiment
            mlflow.set_experiment(config.experiment_name)

            # Wrap DSPy module classes if available
            if DSPY_AVAILABLE:
                self._wrap_dspy_modules()

    def _wrap_dspy_modules(self) -> None:
        """Wrap common DSPy module classes with tracing."""
        module_classes = [
            "Predict",
            "ChainOfThought",
            "ReAct",
            "ProgramOfThought",
            "MultiChainComparison",
            "BootstrapFewShot",
            "BootstrapFewShotWithRandomSearch",
            "BootstrapFinetune",
            "Ensemble",
            "teleprompt",
        ]

        for class_name in module_classes:
            if hasattr(dspy, class_name):
                original_class = getattr(dspy, class_name)
                # Check if it's actually a class (not a module or function)
                if isinstance(original_class, type) and not hasattr(
                    original_class, "_mlflow_wrapped"
                ):
                    wrapped_class = self._create_wrapped_class(original_class)
                    setattr(dspy, class_name, wrapped_class)
                    original_class._mlflow_wrapped = True

    def _create_wrapped_class(self, original_class: type) -> type:
        """Create a wrapped version of a DSPy module class."""
        config = self.config

        class WrappedClass(original_class):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                # Wrap the forward method
                if hasattr(self, "forward"):
                    self._original_forward = self.forward
                    self.forward = self._traced_forward

            def _traced_forward(self, *args, **kwargs):
                # Create traced module wrapper
                traced = TracedModule(self, config)
                # Use the original forward method
                traced.module.forward = self._original_forward
                return traced.forward(*args, **kwargs)

        WrappedClass.__name__ = original_class.__name__
        WrappedClass.__qualname__ = original_class.__qualname__
        return WrappedClass

    def flush_traces(self) -> None:
        """Flush buffered traces to MLflow."""
        with self._buffer_lock:
            if self._trace_buffer:
                # In a real implementation, we would batch log to MLflow
                # For now, we'll just clear the buffer
                self._trace_buffer.clear()


def autolog(config: Optional[MLflowDSPyConfig] = None, disable: bool = False) -> MLflowDSPyClient:
    """Enable automatic MLflow tracing for DSPy programs.

    Args:
        config: Configuration for autolog behavior
        disable: If True, disable autolog

    Returns:
        MLflowDSPyClient instance

    """
    global _autolog_client

    with _client_lock:
        if disable:
            if _autolog_client:
                _autolog_client.config.enabled = False
            return _autolog_client

        if _autolog_client is None or config is not None:
            # Create new client or update configuration
            if config is None:
                config = MLflowDSPyConfig.from_env()
            _autolog_client = MLflowDSPyClient(config)

        return _autolog_client


def get_autolog_client() -> Optional[MLflowDSPyClient]:
    """Get the current autolog client instance."""
    return _autolog_client


def disable_autolog() -> None:
    """Disable MLflow DSPy autolog."""
    autolog(disable=True)
