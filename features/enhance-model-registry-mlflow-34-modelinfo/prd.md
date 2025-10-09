# Product Requirements Document: Enhance Model Registry with MLflow 3.4 ModelInfo

## Objectives

Upgrade HokusaiModelRegistry to leverage MLflow 3.4's enhanced ModelInfo entity for improved model tracking, lineage, and metadata management while preserving the critical webhook integration for marketplace notifications.

Key improvements:
- Better model identification using unique model_uuid
- Schema validation through model signatures
- Structured metadata without character limits
- Git-based lineage for contributor attribution
- Improved model searchability

## Background

Hokusai has upgraded from MLflow 2.9.2 to 3.4.0, but the current implementation in `src/services/model_registry.py` only uses 2.9.2-era APIs. MLflow 3.4 introduces the ModelInfo object with enhanced capabilities that remain unused.

Current limitations:
- Ignoring ModelInfo object returned by log_model()
- Storing metadata in params (limited to strings, 500-char limit)
- No input/output schema validation
- Manual JSON parsing for model history
- No unique model UUID for precise tracking

Critical constraint: The `mlflow.register_model()` call must be preserved as it provides the ModelVersion object with the version number required for webhook payloads sent to hokusai-site marketplace.

## Target Personas

1. Data Scientists: Need better model tracking and lineage
2. ML Engineers: Need schema validation and structured metadata
3. Platform Engineers: Need reliable webhook integration
4. Contributors: Need attribution through git lineage

## Success Criteria

### Functional Requirements

1. `register_baseline()` captures and returns ModelInfo fields
2. `register_improved_model()` captures and returns ModelInfo fields
3. Model signatures validated on registration (reject invalid inputs)
4. `model_uuid` stored as model version tag for searchability
5. New method: `get_model_by_uuid(uuid: str)` for UUID-based lookup
6. Webhook integration unchanged - still sends `model_version.version`
7. Existing callers work without changes (backward compatible)

### Non-Functional Requirements

1. No breaking changes to webhook payload schema
2. Performance impact < 5% (ModelInfo capture is in-memory)
3. Upgrade path documented for existing models
4. Type hints for ModelInfo and ModelVersion objects

## Technical Implementation

### Affected Files

1. `src/services/model_registry.py` - Core registry implementation
   - `register_baseline()` - Line 38-102
   - `register_improved_model()` - Line 104-178
   - `get_model_lineage()` - Line 180-237 (simplify with metadata)
   - `get_contributor_models()` - Line 299-358 (remove JSON parsing)
   - New: `get_model_by_uuid()` method

2. `tests/unit/test_model_registry_hooks.py` - Update assertions for new fields

3. `tests/integration/test_model_registration_integration.py` - Verify webhook payloads

### Core Changes

#### Enhanced register_baseline() Method

Update the method signature to accept:
- `signature: Optional[ModelSignature]` - Input/output schema
- `input_example: Optional[Any]` - Schema inference example
- `code_paths: Optional[list[str]]` - Git lineage tracking

Capture both ModelInfo (for tracking) and ModelVersion (for webhooks):

```python
def register_baseline(
    self,
    model: Any,
    model_type: str,
    metadata: dict[str, Any],
    signature: Optional[ModelSignature] = None,
    input_example: Optional[Any] = None,
    code_paths: Optional[list[str]] = None
) -> dict[str, Any]:
    """Register baseline with MLflow 3.4 ModelInfo + webhook support."""
```

Implementation steps:
1. Log params for filtering/search
2. Create structured metadata dictionary (no char limits)
3. Capture ModelInfo from `mlflow.pyfunc.log_model()`
4. Get ModelVersion from `mlflow.register_model()` (CRITICAL - DO NOT REMOVE)
5. Store model_uuid as tag for searchability
6. Merge both objects into result dictionary

#### New get_model_by_uuid() Method

```python
def get_model_by_uuid(self, model_uuid: str) -> Optional[dict[str, Any]]:
    """Retrieve model by UUID for precise tracking."""
```

Search models by UUID tag and return comprehensive model information.

#### Webhook Payload Enhancement

The webhook payload remains backward compatible but gains optional new fields:
- `model_uuid` - Unique identifier
- `model_uri` - Model location
- `signature` - Input/output schema
- `metadata` - Structured metadata

### Data Schema

Enhanced result dictionary from register_baseline():

```python
{
    # Existing fields (webhook compatibility)
    "model_id": str,                    # "model_name/version"
    "model_name": str,                  # From ModelVersion
    "version": str,                     # From ModelVersion (CRITICAL)
    "model_type": str,
    "is_baseline": bool,
    "run_id": str,
    "registration_timestamp": str,

    # NEW: ModelInfo enhancements
    "model_uri": str,                   # Unique model location
    "model_uuid": str,                  # Unique identifier
    "artifact_path": str,               # Artifact location
    "flavors": list[str],               # Model flavors
    "signature": Optional[str],         # I/O schema
    "mlflow_version": str,              # MLflow version used
    "metadata": dict[str, Any],         # Structured metadata
}
```

## Testing Requirements

### Unit Tests

1. **test_register_baseline_captures_model_info**
   - Verify ModelInfo fields are captured
   - Assert existing fields present (webhook compatibility)
   - Assert new ModelInfo fields present
   - Verify metadata structure

2. **test_webhook_payload_unchanged**
   - Verify webhook receives required fields
   - Assert version number from ModelVersion present
   - Confirm no breaking changes

3. **test_get_model_by_uuid**
   - Register model and capture UUID
   - Retrieve by UUID
   - Verify returned data matches

4. **test_signature_validation**
   - Register with valid signature
   - Attempt registration with invalid signature
   - Verify validation errors

5. **test_backward_compatibility**
   - Register without new optional parameters
   - Verify existing functionality works
   - Assert no errors

### Integration Tests

1. **test_model_registration_with_webhook_emission**
   - End-to-end registration + webhook notification
   - Verify webhook payload contains version from ModelVersion
   - Verify new optional fields present

2. **test_model_uuid_searchability**
   - Register multiple models
   - Search by UUID
   - Verify correct model retrieved

## Migration Guide

### For Existing Code

Existing code continues to work unchanged:

```python
# Before (still works)
result = registry.register_baseline(
    model=model,
    model_type="lead_scoring",
    metadata={"framework": "sklearn"}
)
```

To enable enhancements:

```python
# After (with enhancements)
from mlflow.models import infer_signature

signature = infer_signature(X_train, y_pred)

result = registry.register_baseline(
    model=model,
    model_type="lead_scoring",
    metadata={
        "framework": "sklearn",
        "dataset_size": len(X_train),
        "features": X_train.columns.tolist()
    },
    signature=signature,
    input_example=X_train[:5]
)

# Access new fields
print(f"Model UUID: {result['model_uuid']}")
print(f"Signature: {result['signature']}")
```

### For Webhook Consumers

Webhook consumers (hokusai-site) will receive backward-compatible payloads with optional new fields. No changes required unless new fields are desired.

## Implementation Checklist

1. Verify MLflow 3.4.0 installed
2. Update `register_baseline()` to capture ModelInfo
3. Update `register_improved_model()` to capture ModelInfo
4. Add `get_model_by_uuid()` method
5. Store model_uuid as model version tag
6. Update type hints (import ModelInfo)
7. Add unit tests for new fields
8. Add integration tests for webhooks
9. Verify backward compatibility
10. Update documentation

## Critical Constraints

1. DO NOT REMOVE `mlflow.register_model()` call - provides ModelVersion with version number for webhooks
2. PRESERVE webhook payload schema - hokusai-site depends on current structure
3. MAINTAIN backward compatibility - existing callers must work unchanged
4. TEST webhook integration thoroughly - production-critical

## References

- MLflow 3.4.0 Release: https://github.com/mlflow/mlflow/releases/tag/v3.4.0
- ModelInfo API: https://mlflow.org/docs/latest/python_api/mlflow.models.html#mlflow.models.ModelInfo
- Model Signatures: https://mlflow.org/docs/latest/models.html#model-signature
- Current implementation: `src/services/model_registry.py`
- Webhook system: `src/events/publishers/webhook_publisher.py`
