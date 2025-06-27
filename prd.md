# Product Requirements Document: Token-Aware MLflow Model Registry

## Objective
Extend the MLflow model registration functionality to include Hokusai-specific metadata that tracks token associations, performance metrics, and baseline values for each model version.

## Problem Statement
Currently, MLflow model registry lacks the ability to associate models with Hokusai tokens and track their performance benchmarks in a standardized way. This makes it difficult to:
- Link model versions to their corresponding Hokusai tokens
- Track baseline performance values for comparison
- Identify which performance metric is being optimized
- Maintain consistent metadata across the Hokusai ecosystem

## Solution Overview
Implement an enhanced model registration system that:
1. Extends MLflow's register_model functionality with required Hokusai metadata
2. Enforces a schema for token-related tags
3. Provides a helper function for simplified registration
4. Integrates with existing MLflow infrastructure

## Key Requirements

### Functional Requirements
1. **Enhanced Model Registration**
   - Accept Hokusai token ID during model registration
   - Store performance metric name (e.g., "reply_rate", "conversion_rate")
   - Record baseline performance value for comparison
   - Maintain compatibility with standard MLflow features

2. **Helper Function Implementation**
   - Create `register_tokenized_model()` function
   - Validate required tags before registration
   - Provide clear error messages for missing metadata
   - Support both new registrations and version updates

3. **Schema Enforcement**
   - Define required tag schema
   - Validate tag formats and values
   - Ensure consistency across registrations
   - Support extensibility for future metadata

### Technical Requirements
1. **Integration**
   - Work with existing MLflow tracking server
   - Compatible with current pipeline infrastructure
   - Support both local and remote model registries

2. **Data Structure**
   - Tags stored as key-value pairs in MLflow
   - Performance values stored as strings (convertible to float)
   - Token IDs follow Hokusai naming conventions

## Implementation Details

### Tag Schema
```python
required_tags = {
    "hokusai_token_id": str,      # e.g., "msg-ai"
    "benchmark_metric": str,       # e.g., "reply_rate"
    "benchmark_value": str,        # e.g., "0.1342"
}
```

### API Example
```python
mlflow.register_model(
    model_uri="runs:/<run-id>/model",
    name="MSG-AI",
    tags={
        "hokusai_token_id": "msg-ai",
        "benchmark_metric": "reply_rate",
        "benchmark_value": "0.1342",
    }
)
```

### Helper Function
```python
register_tokenized_model(
    model_uri="runs:/<run-id>/model",
    model_name="MSG-AI",
    token_id="msg-ai",
    metric_name="reply_rate",
    baseline_value=0.1342
)
```

## Success Criteria
1. Models can be registered with Hokusai-specific metadata
2. Required tags are validated and enforced
3. Helper function simplifies the registration process
4. Existing MLflow functionality remains intact
5. Clear documentation and examples provided

## Deliverables
1. Implementation of `register_tokenized_model()` function
2. Schema validation logic for required tags
3. Integration with existing model registry
4. Unit tests for new functionality
5. Documentation updates
6. Example usage in pipeline code