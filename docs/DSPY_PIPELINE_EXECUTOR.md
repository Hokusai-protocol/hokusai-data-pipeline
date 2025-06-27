# DSPy Pipeline Executor

The DSPy Pipeline Executor provides a runtime environment for executing DSPy (Declarative Self-Prompting) programs within the Hokusai ML platform. It offers structured execution, comprehensive logging, MLflow integration, and a RESTful API for easy access.

## Overview

The DSPy Pipeline Executor enables:
- **Structured Execution**: Run DSPy programs with input validation and error handling
- **MLflow Integration**: Automatic tracking of executions, parameters, and outputs
- **Batch Processing**: Execute programs on multiple inputs in parallel
- **Caching**: Cache programs and results for improved performance
- **Multiple Modes**: Support for normal, dry-run, and debug execution modes
- **RESTful API**: Easy integration with other services via HTTP endpoints

## Architecture

```
┌─────────────────────┐
│   REST API Layer    │
│  (/api/v1/dspy/*)   │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ DSPyPipelineExecutor│
│  - Input Validation │
│  - Program Loading  │
│  - Execution Engine │
│  - Result Caching   │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │             │
┌───▼────┐  ┌────▼────┐
│MLflow   │  │  DSPy   │
│Tracking │  │Programs │
└─────────┘  └─────────┘
```

## Installation

The DSPy Pipeline Executor is included in the Hokusai ML Platform package:

```bash
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

## Usage

### Python API

```python
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor, ExecutionMode

# Initialize executor
executor = DSPyPipelineExecutor(
    cache_enabled=True,
    mlflow_tracking=True,
    timeout=300,
    max_retries=2
)

# Execute a DSPy program
result = executor.execute(
    model_id="email-assistant-v1",
    inputs={
        "recipient": "john@example.com",
        "subject": "Meeting Follow-up",
        "context": "Discussed Q4 targets"
    },
    mode=ExecutionMode.NORMAL
)

if result.success:
    print(f"Generated email: {result.outputs['email_body']}")
else:
    print(f"Execution failed: {result.error}")
```

### Batch Execution

```python
# Execute on multiple inputs
batch_inputs = [
    {"recipient": "john@example.com", "subject": "Meeting"},
    {"recipient": "jane@example.com", "subject": "Update"},
    {"recipient": "bob@example.com", "subject": "Report"}
]

results = executor.execute_batch(
    model_id="email-assistant-v1",
    inputs_list=batch_inputs
)

for i, result in enumerate(results):
    print(f"Result {i+1}: {'Success' if result.success else 'Failed'}")
```

### REST API

The executor provides a comprehensive REST API for integration:

#### Execute Single Input

```bash
curl -X POST http://localhost:8001/api/v1/dspy/execute \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "program_id": "email-assistant-v1",
    "inputs": {
      "recipient": "john@example.com",
      "subject": "Meeting Follow-up",
      "context": "Discussed Q4 targets"
    },
    "mode": "normal"
  }'
```

#### Execute Batch

```bash
curl -X POST http://localhost:8001/api/v1/dspy/execute/batch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "program_id": "email-assistant-v1",
    "inputs_list": [
      {"recipient": "john@example.com", "subject": "Meeting"},
      {"recipient": "jane@example.com", "subject": "Update"}
    ]
  }'
```

#### List Available Programs

```bash
curl -X GET http://localhost:8001/api/v1/dspy/programs \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Get Execution Statistics

```bash
curl -X GET http://localhost:8001/api/v1/dspy/stats \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Execution Modes

The executor supports three execution modes:

### Normal Mode
Standard execution with full processing and MLflow tracking:
```python
result = executor.execute(
    program=my_program,
    inputs={"text": "Process this"},
    mode=ExecutionMode.NORMAL
)
```

### Dry-Run Mode
Validates inputs without executing the program:
```python
result = executor.execute(
    program=my_program,
    inputs={"text": "Validate this"},
    mode=ExecutionMode.DRY_RUN
)
# result.success indicates if inputs are valid
```

### Debug Mode
Enables verbose logging and captures detailed execution traces:
```python
result = executor.execute(
    program=my_program,
    inputs={"text": "Debug this"},
    mode=ExecutionMode.DEBUG
)
# result.metadata['debug_trace'] contains detailed information
```

## Configuration

### Environment Variables

Configure the executor through environment variables:

```bash
# MLflow Configuration
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_EXPERIMENT_NAME=dspy-execution

# Pipeline Configuration
PIPELINE_LOG_LEVEL=INFO
MAX_WORKERS=4

# API Configuration
API_HOST=0.0.0.0
API_PORT=8001
SECRET_KEY=your-secret-key
```

### Programmatic Configuration

```python
executor = DSPyPipelineExecutor(
    cache_enabled=True,          # Enable result caching
    mlflow_tracking=True,        # Enable MLflow tracking
    timeout=300,                 # Execution timeout in seconds
    max_retries=2,              # Retry attempts for failures
    max_workers=4               # Workers for batch execution
)
```

## Integration with DSPy Model Loader

The executor seamlessly integrates with the DSPy Model Loader:

```python
from src.services.dspy_model_loader import DSPyModelLoader

# Load a DSPy program
loader = DSPyModelLoader()
program_data = loader.load_from_config("configs/email_assistant.yaml")

# Execute the loaded program
result = executor.execute(
    program=program_data['program'],
    inputs={"recipient": "test@example.com"}
)
```

## MLflow Integration

All executions are automatically tracked in MLflow:

### Logged Parameters
- `program_name`: Name of the executed DSPy program
- `mode`: Execution mode (normal, dry_run, debug)
- `input_keys`: List of input field names
- Output samples (first 5 fields, truncated to 100 chars)

### Logged Metrics
- `execution_time`: Time taken for execution in seconds
- `success`: 1.0 for success, 0.0 for failure

### Viewing Results

Access the MLflow UI to view execution history:
```bash
mlflow ui --host 0.0.0.0 --port 5000
```

## Error Handling

The executor provides comprehensive error handling:

```python
result = executor.execute(
    model_id="invalid-program",
    inputs={"test": "data"}
)

if not result.success:
    print(f"Error: {result.error}")
    # Possible errors:
    # - "Model invalid-program not found in registry"
    # - "Missing required input fields: ['field1', 'field2']"
    # - "Execution timeout after 300 seconds"
```

## Performance Optimization

### Caching

The executor caches both programs and results:

```python
# First execution loads and caches the program
result1 = executor.execute(model_id="cached-program", inputs={"a": 1})

# Subsequent executions use cached program (faster)
result2 = executor.execute(model_id="cached-program", inputs={"a": 2})

# Clear cache when needed
executor.clear_cache()
```

### Batch Processing

Batch execution runs multiple inputs in parallel:

```python
# Process 100 inputs in parallel (using max_workers)
results = executor.execute_batch(
    model_id="fast-program",
    inputs_list=[{"input": i} for i in range(100)]
)
```

## Monitoring and Statistics

Track executor performance with built-in statistics:

```python
stats = executor.get_execution_stats()
print(f"Total executions: {stats['total_executions']}")
print(f"Success rate: {stats['success_rate']:.2%}")
print(f"Average time: {stats['average_execution_time']:.2f}s")
print(f"P95 time: {stats['p95_execution_time']:.2f}s")
```

## API Reference

### DSPyPipelineExecutor

#### `__init__(cache_enabled=True, mlflow_tracking=True, timeout=300, max_retries=1, max_workers=4)`
Initialize the executor with configuration options.

#### `execute(program=None, model_id=None, inputs=None, mode=ExecutionMode.NORMAL)`
Execute a DSPy program with given inputs.

**Parameters:**
- `program`: DSPy program instance (optional if model_id provided)
- `model_id`: ID of registered program (optional if program provided)
- `inputs`: Dictionary of input data
- `mode`: Execution mode (NORMAL, DRY_RUN, DEBUG)

**Returns:** `ExecutionResult` object with:
- `success`: Boolean indicating success
- `outputs`: Dictionary of program outputs (if successful)
- `error`: Error message (if failed)
- `execution_time`: Time taken in seconds
- `program_name`: Name of executed program
- `metadata`: Additional execution metadata

#### `execute_batch(program=None, model_id=None, inputs_list=None)`
Execute program on multiple inputs in parallel.

**Returns:** List of `ExecutionResult` objects

#### `get_execution_stats()`
Get execution statistics.

**Returns:** Dictionary with statistics

#### `clear_cache()`
Clear program and result caches.

#### `shutdown()`
Shutdown executor and cleanup resources.

### REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/dspy/execute` | POST | Execute single input |
| `/api/v1/dspy/execute/batch` | POST | Execute batch of inputs |
| `/api/v1/dspy/programs` | GET | List available programs |
| `/api/v1/dspy/execution/{id}` | GET | Get execution details |
| `/api/v1/dspy/stats` | GET | Get execution statistics |
| `/api/v1/dspy/cache/clear` | POST | Clear caches |
| `/api/v1/dspy/health` | GET | Health check |

## Troubleshooting

### Common Issues

1. **MLflow Connection Failed**
   ```
   WARNING: Failed to initialize MLflow tracking
   ```
   Solution: Ensure MLflow server is running and MLFLOW_TRACKING_URI is correct.

2. **Program Not Found**
   ```
   Error: Model xyz not found in registry
   ```
   Solution: Verify the program is registered in the model registry.

3. **Timeout Errors**
   ```
   Error: Execution timeout after 300 seconds
   ```
   Solution: Increase timeout or optimize the DSPy program.

4. **Input Validation Errors**
   ```
   Error: Missing required input fields: ['field1']
   ```
   Solution: Ensure all required fields are provided in the input dictionary.

### Debug Tips

1. Enable debug logging:
   ```python
   import logging
   logging.getLogger('src.services.dspy_pipeline_executor').setLevel(logging.DEBUG)
   ```

2. Use debug mode for detailed traces:
   ```python
   result = executor.execute(
       program=my_program,
       inputs=inputs,
       mode=ExecutionMode.DEBUG
   )
   print(result.metadata['debug_trace'])
   ```

3. Check MLflow UI for execution history and logs.

## Examples

### Email Generation Example

```python
# Load email assistant program
result = executor.execute(
    model_id="email-assistant-v1",
    inputs={
        "recipient": "client@company.com",
        "subject": "Project Update",
        "context": "Milestone 1 completed ahead of schedule"
    }
)

if result.success:
    print(result.outputs['email_body'])
```

### Text Summarization Example

```python
# Batch summarization
documents = [
    {"text": "Long document 1..."},
    {"text": "Long document 2..."},
    {"text": "Long document 3..."}
]

results = executor.execute_batch(
    model_id="summarizer-v2",
    inputs_list=documents
)

for i, result in enumerate(results):
    if result.success:
        print(f"Summary {i+1}: {result.outputs['summary']}")
```

### Integration with Metaflow

```python
from metaflow import FlowSpec, step

class DSPyFlow(FlowSpec):
    @step
    def start(self):
        self.data = load_data()
        self.next(self.process)
    
    @step
    def process(self):
        executor = DSPyPipelineExecutor()
        self.results = executor.execute_batch(
            model_id="processor-v1",
            inputs_list=self.data
        )
        self.next(self.end)
    
    @step
    def end(self):
        successful = sum(1 for r in self.results if r.success)
        print(f"Processed {successful}/{len(self.results)} successfully")
```

## Contributing

When contributing to the DSPy Pipeline Executor:

1. Add tests for new features
2. Update documentation
3. Follow the existing code style
4. Ensure all tests pass
5. Update the API version if making breaking changes