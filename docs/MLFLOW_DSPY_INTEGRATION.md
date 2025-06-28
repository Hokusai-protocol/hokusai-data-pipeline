# MLflow DSPy Integration Guide

This guide covers the integration of MLflow tracing with DSPy programs in the Hokusai platform, enabling automatic capture of inputs, outputs, and execution traces.

## Overview

The MLflow DSPy integration provides automatic tracing for all DSPy program executions without requiring manual instrumentation. This enables:

- Complete visibility into prompt-based model operations
- Performance monitoring and debugging
- Execution history and replay capabilities
- Integration with MLflow's experiment tracking

## Quick Start

### Basic Usage

```python
from src.integrations.mlflow_dspy import autolog
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor

# Enable automatic tracing
autolog()

# Execute DSPy programs - they will be automatically traced
executor = DSPyPipelineExecutor()
result = executor.execute(
    program=DraftText(),
    inputs={"topic": "AI safety", "requirements": "200 words"}
)
```

### Environment Configuration

Set environment variables to configure tracing behavior:

```bash
export MLFLOW_DSPY_ENABLED=true
export MLFLOW_DSPY_SAMPLING_RATE=0.1  # Trace 10% of executions
export MLFLOW_DSPY_EXPERIMENT=dspy-production
export MLFLOW_DSPY_BUFFER_SIZE=100
```

## Configuration Options

### MLflowDSPyConfig

The `MLflowDSPyConfig` class provides fine-grained control over tracing behavior:

```python
from src.integrations.mlflow_dspy import MLflowDSPyConfig, autolog

config = MLflowDSPyConfig(
    enabled=True,                    # Enable/disable tracing
    log_inputs=True,                 # Log input parameters
    log_outputs=True,                # Log output values
    log_signatures=True,             # Log signature information
    log_intermediate_steps=True,     # Log intermediate computations
    sampling_rate=1.0,               # Fraction of executions to trace (0.0-1.0)
    trace_buffer_size=100,           # Buffer size for batch uploads
    experiment_name="dspy-traces",   # MLflow experiment name
    custom_tags={"team": "ml"}       # Custom tags for all traces
)

autolog(config=config)
```

### Configuration Methods

1. **Programmatic Configuration**
   ```python
   config = MLflowDSPyConfig(sampling_rate=0.5)
   autolog(config=config)
   ```

2. **Environment Variables**
   ```python
   # Automatically reads from environment
   autolog()  # Uses MLflowDSPyConfig.from_env()
   ```

3. **Runtime Updates**
   ```python
   # Disable tracing temporarily
   from src.integrations.mlflow_dspy import disable_autolog
   disable_autolog()
   
   # Re-enable with new config
   autolog(MLflowDSPyConfig(sampling_rate=0.1))
   ```

## Traced Information

### Automatic Capture

The integration automatically captures:

1. **Input Parameters**
   - All positional and keyword arguments
   - Type information for each parameter
   - Serialized values (with size limits for large objects)

2. **Output Values**
   - Return values from DSPy modules
   - Structured outputs with field names
   - Type information for outputs

3. **Signature Information**
   - Input field definitions
   - Output field definitions
   - Field types and constraints
   - Required vs optional fields

4. **Execution Metadata**
   - Module name and type
   - Execution timestamp
   - Duration in milliseconds
   - Error information (if any)

### Custom Metadata

Add custom metadata to traces:

```python
from src.integrations.mlflow_dspy import TracedModule

# Create traced module with custom metadata
traced = TracedModule(my_dspy_module)
traced.set_metadata({
    "user_id": "12345",
    "session_id": "abc-def",
    "model_version": "v2.1"
})

result = traced.forward(input_text="Hello")
```

## Performance Considerations

### Sampling

Control the fraction of executions that are traced:

```python
# Trace only 10% of executions in production
config = MLflowDSPyConfig(sampling_rate=0.1)
```

Sampling is deterministic per execution to ensure consistency.

### Buffering

Traces are buffered to reduce overhead:

```python
# Buffer up to 200 traces before flushing
config = MLflowDSPyConfig(trace_buffer_size=200)
```

### Overhead

The tracing integration is designed for minimal overhead:
- < 5% execution time overhead with full tracing
- < 1% overhead with 10% sampling rate
- Negligible memory usage with appropriate buffer sizes

## Integration with DSPy Components

### Pipeline Executor

The DSPy Pipeline Executor automatically enables tracing:

```python
executor = DSPyPipelineExecutor(mlflow_tracking=True)
# Tracing is automatically enabled for all executions
```

### Model Loader

Models loaded through the DSPy Model Loader preserve tracing configuration:

```python
loader = DSPyModelLoader()
program = loader.load_from_config("config.yaml")
# Tracing configuration is preserved
```

### Signature Library

All signatures from the library are automatically traced:

```python
from src.dspy_signatures import EmailDraft

# This will be traced automatically
email_program = EmailDraft()
result = executor.execute(email_program, inputs={...})
```

## Viewing Traces

### MLflow UI

View traces in the MLflow UI:

```bash
mlflow ui --port 5000
```

Navigate to the experiment and click on a run to see:
- Trace timeline view
- Input/output values
- Execution hierarchy
- Performance metrics

### Programmatic Access

Access trace data programmatically:

```python
import mlflow

# Get traces for a run
run_id = "abc123..."
client = mlflow.tracking.MlflowClient()
traces = client.get_traces(run_id)

for trace in traces:
    print(f"Module: {trace.name}")
    print(f"Duration: {trace.duration_ms}ms")
    print(f"Inputs: {trace.inputs}")
    print(f"Outputs: {trace.outputs}")
```

## Troubleshooting

### Tracing Not Working

1. **Check if enabled**:
   ```python
   from src.integrations.mlflow_dspy import get_autolog_client
   client = get_autolog_client()
   print(f"Enabled: {client.config.enabled if client else False}")
   ```

2. **Verify MLflow connection**:
   ```python
   import mlflow
   print(f"Tracking URI: {mlflow.get_tracking_uri()}")
   ```

3. **Check sampling rate**:
   ```python
   print(f"Sampling rate: {client.config.sampling_rate}")
   ```

### Performance Issues

1. **Reduce sampling rate**:
   ```python
   autolog(MLflowDSPyConfig(sampling_rate=0.01))  # 1% sampling
   ```

2. **Disable expensive logging**:
   ```python
   config = MLflowDSPyConfig(
       log_intermediate_steps=False,
       log_signatures=False
   )
   ```

3. **Increase buffer size**:
   ```python
   config = MLflowDSPyConfig(trace_buffer_size=500)
   ```

### Missing Data

1. **Check log configuration**:
   ```python
   config = MLflowDSPyConfig(
       log_inputs=True,
       log_outputs=True,
       log_signatures=True
   )
   ```

2. **Verify module compatibility**:
   - Ensure DSPy modules have proper `forward` methods
   - Check that signatures are properly defined

## Best Practices

1. **Production Settings**
   ```python
   # Production configuration
   config = MLflowDSPyConfig(
       sampling_rate=0.1,              # 10% sampling
       trace_buffer_size=200,          # Larger buffer
       log_intermediate_steps=False,   # Reduce verbosity
       experiment_name="dspy-prod"
   )
   ```

2. **Development Settings**
   ```python
   # Development configuration
   config = MLflowDSPyConfig(
       sampling_rate=1.0,              # Trace everything
       log_intermediate_steps=True,    # Full visibility
       experiment_name="dspy-dev"
   )
   ```

3. **Debugging**
   ```python
   # Debug configuration
   config = MLflowDSPyConfig(
       sampling_rate=1.0,
       log_intermediate_steps=True,
       custom_tags={"debug": "true", "issue": "JIRA-123"}
   )
   ```

4. **A/B Testing**
   ```python
   # Tag different variants
   config_a = MLflowDSPyConfig(custom_tags={"variant": "A"})
   config_b = MLflowDSPyConfig(custom_tags={"variant": "B"})
   ```

## Advanced Usage

### Custom Trace Processing

```python
from src.integrations.mlflow_dspy import autolog, get_autolog_client

# Custom trace processor
def process_trace(trace_data):
    # Custom logic for trace processing
    if trace_data["duration_ms"] > 1000:
        alert_slow_execution(trace_data)

# Get client and add processor
client = get_autolog_client()
client.add_trace_processor(process_trace)
```

### Trace Filtering

```python
# Only trace specific modules
config = MLflowDSPyConfig(
    module_filter=lambda name: name in ["EmailDraft", "ReviseText"]
)
```

### Conditional Tracing

```python
# Trace based on input conditions
def should_trace(inputs):
    return inputs.get("debug", False) or inputs.get("user_type") == "beta"

config = MLflowDSPyConfig(
    trace_condition=should_trace
)
```

## Migration Guide

### From Manual MLflow Logging

Before:
```python
with mlflow.start_run():
    mlflow.log_param("input_text", text)
    result = dspy_program(text)
    mlflow.log_metric("output_length", len(result))
```

After:
```python
autolog()  # That's it!
result = dspy_program(text)
```

### From Custom Tracing

Before:
```python
def traced_execution(program, inputs):
    start = time.time()
    try:
        result = program(**inputs)
        log_trace(inputs, result, time.time() - start)
        return result
    except Exception as e:
        log_error(e)
        raise
```

After:
```python
autolog()
result = program(**inputs)  # Automatically traced
```

## Security and Privacy

### Sensitive Data

Configure what gets logged:

```python
# Don't log potentially sensitive inputs/outputs
config = MLflowDSPyConfig(
    log_inputs=False,
    log_outputs=False,
    log_signatures=True  # Still log structure
)
```

### Data Sanitization

Add custom sanitization:

```python
def sanitize_inputs(inputs):
    # Remove sensitive fields
    safe_inputs = inputs.copy()
    safe_inputs.pop("api_key", None)
    safe_inputs.pop("password", None)
    return safe_inputs

config = MLflowDSPyConfig(
    input_sanitizer=sanitize_inputs
)
```

## Roadmap

Future enhancements planned:

1. **Real-time Monitoring**: Live trace streaming and alerting
2. **Trace Replay**: Replay executions with captured inputs
3. **Performance Profiling**: Detailed performance breakdowns
4. **Distributed Tracing**: Support for distributed DSPy executions
5. **Custom Visualizations**: Enhanced trace visualization options