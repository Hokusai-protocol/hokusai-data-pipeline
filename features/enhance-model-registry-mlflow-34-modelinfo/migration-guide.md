# Migration Guide: MLflow 3.4 ModelInfo Enhancements

This guide explains how to use the new MLflow 3.4 ModelInfo features in the Hokusai Model Registry.

## What Changed

The `HokusaiModelRegistry` now leverages MLflow 3.4's enhanced `ModelInfo` entity to provide:
- **Better model identification** with unique `model_uuid`
- **Schema validation** through model signatures
- **Structured metadata** without character limits
- **Git-based lineage** for contributor attribution
- **Improved searchability** with UUID-based lookups

## Backward Compatibility

**Good news!** Your existing code will continue to work unchanged. All new parameters are optional.

```python
# Old code - still works perfectly
from hokusai.services.model_registry import HokusaiModelRegistry

registry = HokusaiModelRegistry()
result = registry.register_baseline(
    model=trained_model,
    model_type="lead_scoring",
    metadata={"framework": "sklearn"}
)

# Still returns all the fields you expect:
print(result["model_id"])  # "hokusai_lead_scoring_baseline/1"
print(result["version"])   # "1"
```

## New Features

### 1. Model UUID - Unique Identifier

Every registered model now has a unique UUID that never changes, even across runs.

```python
result = registry.register_baseline(
    model=trained_model,
    model_type="classification",
    metadata={"dataset": "customers_v2"}
)

# NEW: Access the model UUID
print(result["model_uuid"])  # "abc123-uuid-456-def"

# NEW: Look up models by UUID
model = registry.get_model_by_uuid("abc123-uuid-456-def")
print(model["model_name"])  # "hokusai_classification_baseline"
```

### 2. Model Signatures - Schema Validation

Add input/output schemas to prevent incompatible model versions from being deployed.

```python
from mlflow.models import infer_signature
import pandas as pd

# Prepare your training data
X_train = pd.DataFrame({
    "age": [25, 30, 35],
    "income": [50000, 60000, 70000]
})
y_train = [0, 1, 1]

# Train your model
model = train_model(X_train, y_train)

# Infer signature from data
predictions = model.predict(X_train)
signature = infer_signature(X_train, predictions)

# Register with signature
result = registry.register_baseline(
    model=model,
    model_type="classification",
    metadata={"dataset": "customers_v2"},
    signature=signature,  # NEW parameter
    input_example=X_train[:2]  # NEW parameter for schema inference
)

# Access signature in result
print(result["signature"])  # "inputs: [age: long, income: long] -> outputs: [prediction: long]"
```

### 3. Structured Metadata - No Limits

The old parameter-based metadata had a 500-character limit. The new structured metadata has no limits and is fully queryable.

```python
# Before (limited to 500 chars, stored as params)
result = registry.register_baseline(
    model=model,
    model_type="classification",
    metadata={"framework": "sklearn"}  # Limited string values only
)

# After (no limits, rich metadata)
result = registry.register_baseline(
    model=model,
    model_type="classification",
    metadata={
        "framework": "scikit-learn",
        "version": "1.4.0",
        "dataset_size": 10000,  # Numbers work!
        "features": ["age", "income", "education"],  # Lists work!
        "training_config": {  # Nested objects work!
            "max_depth": 5,
            "n_estimators": 100
        },
        "description": "Long description that exceeds 500 characters..." * 10  # No limit!
    }
)

# Access rich metadata
print(result["metadata"])  # Full nested structure preserved
```

### 4. Code Paths - Git Lineage

Track which code files were used to train the model for contributor attribution.

```python
result = registry.register_baseline(
    model=model,
    model_type="classification",
    metadata={"framework": "sklearn"},
    code_paths=[  # NEW parameter
        "src/models/classifier.py",
        "src/features/engineering.py"
    ]
)

# MLflow will track the git commit for attribution
```

### 5. UUID-Based Model Lookup

Find models by their unique UUID instead of name/version.

```python
# Get model by UUID
model = registry.get_model_by_uuid("abc123-uuid-456-def")

if model:
    print(f"Found: {model['model_name']} v{model['version']}")
    print(f"Stage: {model['stage']}")
    print(f"Run ID: {model['run_id']}")
else:
    print("Model not found")
```

## Complete Example: Before and After

### Before (Still Works!)

```python
from hokusai.services.model_registry import HokusaiModelRegistry
from sklearn.ensemble import RandomForestClassifier

# Train model
model = RandomForestClassifier(n_estimators=100)
model.fit(X_train, y_train)

# Register (old way)
registry = HokusaiModelRegistry()
result = registry.register_baseline(
    model=model,
    model_type="classification",
    metadata={"framework": "sklearn", "accuracy": "0.85"}
)

print(result["model_id"])  # Works as before
```

### After (With New Features!)

```python
from hokusai.services.model_registry import HokusaiModelRegistry
from sklearn.ensemble import RandomForestClassifier
from mlflow.models import infer_signature

# Train model
model = RandomForestClassifier(n_estimators=100)
model.fit(X_train, y_train)

# Infer signature
predictions = model.predict(X_train)
signature = infer_signature(X_train, predictions)

# Register (new way)
registry = HokusaiModelRegistry()
result = registry.register_baseline(
    model=model,
    model_type="classification",
    metadata={
        "framework": "scikit-learn",
        "version": "1.4.0",
        "accuracy": 0.85,  # Now a number!
        "dataset_size": len(X_train),
        "features": X_train.columns.tolist(),
        "hyperparameters": {
            "n_estimators": 100,
            "max_depth": 5
        }
    },
    signature=signature,  # Schema validation
    input_example=X_train[:5],  # Example for inference
    code_paths=["src/models/classifier.py"]  # Git lineage
)

# Access new fields
print(f"Model ID: {result['model_id']}")  # Old field
print(f"Model UUID: {result['model_uuid']}")  # NEW field
print(f"Model URI: {result['model_uri']}")  # NEW field
print(f"Signature: {result['signature']}")  # NEW field
print(f"Flavors: {result['flavors']}")  # NEW field
print(f"MLflow Version: {result['mlflow_version']}")  # NEW field

# Look up by UUID later
model_info = registry.get_model_by_uuid(result['model_uuid'])
```

## Result Dictionary Structure

### Old Fields (Still Present)

```python
{
    "model_id": "hokusai_classification_baseline/1",
    "model_name": "hokusai_classification_baseline",
    "version": "1",  # CRITICAL for webhooks
    "model_type": "classification",
    "is_baseline": True,
    "run_id": "abc123",
    "registration_timestamp": "2025-10-09T10:00:00"
}
```

### New Fields (MLflow 3.4)

```python
{
    # ...all old fields above...
    "model_uri": "runs:/abc123/model",
    "model_uuid": "unique-uuid-456",  # NEW
    "artifact_path": "model",
    "flavors": ["python_function", "sklearn"],
    "signature": "inputs: [...] -> outputs: [...]",  # NEW
    "mlflow_version": "3.4.0",
    "metadata": {  # Rich structured metadata
        "framework": "scikit-learn",
        "dataset_size": 10000,
        # ...any other metadata you provided...
    }
}
```

## Improved Model Registration

The same enhancements apply to `register_improved_model()`:

```python
# Register improved model with new features
result = registry.register_improved_model(
    model=improved_model,
    baseline_id="hokusai_classification_baseline/1",
    delta_metrics={"accuracy": 0.05},
    contributor="0x1234567890123456789012345678901234567890",
    signature=signature,  # NEW
    input_example=X_train[:5],  # NEW
    code_paths=["src/models/improved_classifier.py"]  # NEW
)

# Access all the same new fields
print(result["model_uuid"])
print(result["signature"])
```

## For Webhook Consumers (hokusai-site)

Webhook payloads now include optional new fields (backward compatible):

```json
{
  "model_id": "hokusai_lead_scoring_baseline/3",
  "model_name": "hokusai_lead_scoring_baseline",
  "version": "3",
  "model_version": "3",
  "mlflow_run_id": "abc123",

  "_comment": "NEW optional fields below",
  "model_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "model_uri": "runs:/abc123/model",
  "signature": "inputs: [...] -> outputs: [...]",
  "metadata": {
    "framework": "scikit-learn",
    "dataset_size": 10000
  }
}
```

## Troubleshooting

### "No module named 'mlflow.models.model'"

Make sure you have MLflow 3.4.0 installed:

```bash
pip install mlflow==3.4.0
```

### "Signature validation error"

If you get signature validation errors, your input data doesn't match the signature. Either:
1. Fix your input data to match the signature
2. Don't provide a signature if you want to skip validation

### "Model UUID not found"

Model UUIDs are only available for models registered after this upgrade. Old models won't have UUIDs.

## Best Practices

1. **Always provide signatures for production models** - This prevents incompatible versions
2. **Use rich metadata** - No more 500-char limits, include everything useful
3. **Track code paths** - Helps with contributor attribution
4. **Use UUID for cross-run tracking** - More reliable than name/version

## Questions?

Check the Hokusai documentation at https://docs.hokus.ai or ask in Discord.
