---
id: model-registry
title: Token-Aware Model Registry
sidebar_label: Model Registry
sidebar_position: 1
---

# Token-Aware Model Registry

The Hokusai Model Registry extends MLflow's model registry with blockchain token awareness, enabling automatic reward distribution for model improvements.

## Overview

The Model Registry serves as the central hub for:
- Registering models with associated Hokusai tokens
- Tracking model lineage and improvements
- Managing model versions and metadata
- Enabling reward distribution for contributors

### Prerequisites

Before using the Model Registry, you need:
1. **Hokusai API Key**: Obtain from https://hokus.ai/settings/api
2. **Python 3.8+**: Required for the SDK
3. **Trained Model**: Your ML model ready for registration

## Key Concepts

### Token-Aware Registration

Every model in Hokusai is associated with a token that represents ownership and enables rewards:

```python
import os
from hokusai.core import ModelRegistry

# Ensure API key is set
api_key = os.getenv("HOKUSAI_API_KEY")
if not api_key:
    raise ValueError("Please set HOKUSAI_API_KEY environment variable")

registry = ModelRegistry()

# Register a model with token metadata
model_info = registry.register_tokenized_model(
    model_uri="runs:/abc123/model",
    name="sentiment-analyzer",
    token_id="SENT-001",
    benchmark_metric="f1_score",
    benchmark_value="0.85"
)
```

### Required Metadata

When registering a tokenized model, you must provide:

- `token_id`: Unique identifier for the Hokusai token
- `benchmark_metric`: The metric used to measure improvements (e.g., "accuracy", "f1_score")
- `benchmark_value`: Baseline performance value for comparison

## Usage Guide

### Basic Model Registration

```python
import mlflow
import os
from hokusai.core import ModelRegistry

# Set up authentication
api_key = os.getenv("HOKUSAI_API_KEY")
if not api_key:
    print("To get your API key:")
    print("1. Log in to https://hokus.ai")
    print("2. Go to Settings → API Keys")
    print("3. Click 'Generate New Key'")
    raise ValueError("HOKUSAI_API_KEY not set")

# Configure MLflow
mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")
os.environ["MLFLOW_TRACKING_TOKEN"] = api_key

# Initialize registry
registry = ModelRegistry()

# Train and log a model with MLflow
with mlflow.start_run() as run:
    # Your model training code here
    model = train_model(data)
    
    # Log model to MLflow
    mlflow.sklearn.log_model(model, "model")
    
    # Register with Hokusai
    model_uri = f"runs:/{run.info.run_id}/model"
    registered_model = registry.register_tokenized_model(
        model_uri=model_uri,
        name="my-classifier",
        token_id="CLASS-001",
        benchmark_metric="accuracy",
        benchmark_value="0.92"
    )
```

### Registering Multiple Versions

```python
# Register baseline version
baseline = registry.register_tokenized_model(
    model_uri="runs:/baseline_run/model",
    name="image-classifier",
    token_id="IMG-001",
    benchmark_metric="accuracy",
    benchmark_value="0.85"
)

# Register improved version
improved = registry.register_tokenized_model(
    model_uri="runs:/improved_run/model",
    name="image-classifier",
    token_id="IMG-001",
    benchmark_metric="accuracy",
    benchmark_value="0.87",  # Improved!
    tags={
        "contributor": "0x742d35Cc6634C0532925a3b844Bc9e7595f5b4e1",
        "data_contribution": "1000_labeled_images"
    }
)
```

### Retrieving Models

```python
# Get a specific model version
model = registry.get_tokenized_model("image-classifier", version="2")

# List all models for a token
token_models = registry.list_models_by_token("IMG-001")
for model in token_models:
    print(f"{model.name} v{model.version}: {model.tags}")

# Get latest model version
latest = registry.get_latest_model_version("image-classifier")
```

### Model Metadata and Tags

Add custom metadata to track contributions and improvements:

```python
registry.register_tokenized_model(
    model_uri=model_uri,
    name="nlp-model",
    token_id="NLP-001",
    benchmark_metric="perplexity",
    benchmark_value="25.3",
    tags={
        # Contributor information
        "contributor_address": "0x123...",
        "contribution_type": "fine_tuning_data",
        
        # Training details
        "dataset_size": "50000",
        "training_hours": "12",
        "gpu_type": "A100",
        
        # Improvement details
        "improvement_method": "domain_adaptation",
        "previous_version": "1"
    }
)
```

## Token ID Conventions

Follow these naming conventions for token IDs:

```python
# Good token IDs
"MSG-AI"        # Uppercase, hyphenated
"SENT-001"      # With version number
"IMG-DETECT"    # Descriptive suffix

# Invalid token IDs (will be rejected)
"msg_ai"        # Lowercase
"MSGAI"         # No separator
"MSG AI"        # Spaces not allowed
"123-MSG"       # Must start with letter
```

## Integration with DeltaOne

The Model Registry works seamlessly with DeltaOne detection:

```python
from hokusai.evaluation.deltaone_evaluator import detect_delta_one

# Register baseline
registry.register_tokenized_model(
    model_uri="runs:/baseline/model",
    name="predictor",
    token_id="PRED-001",
    benchmark_metric="rmse",
    benchmark_value="0.15"
)

# Register improved version
registry.register_tokenized_model(
    model_uri="runs:/improved/model",
    name="predictor",
    token_id="PRED-001",
    benchmark_metric="rmse",
    benchmark_value="0.13"  # 2pp improvement!
)

# DeltaOne will automatically detect the improvement
if detect_delta_one("predictor"):
    print("DeltaOne achieved! Rewards will be distributed.")
```

## Advanced Features

### Model Lineage Tracking

Track the complete improvement history of a model:

```python
lineage = registry.get_model_lineage("sentiment-analyzer")

for version in lineage:
    print(f"Version {version.version}:")
    print(f"  - Metric: {version.tags['benchmark_value']}")
    print(f"  - Contributor: {version.tags.get('contributor_address', 'N/A')}")
    print(f"  - Timestamp: {version.creation_timestamp}")
```

### Bulk Operations

Register multiple models efficiently:

```python
models_to_register = [
    {
        "uri": "runs:/run1/model",
        "name": "model-a",
        "token_id": "TOK-A",
        "metric": "accuracy",
        "value": "0.85"
    },
    {
        "uri": "runs:/run2/model",
        "name": "model-b",
        "token_id": "TOK-B",
        "metric": "f1_score",
        "value": "0.90"
    }
]

for model_info in models_to_register:
    registry.register_tokenized_model(
        model_uri=model_info["uri"],
        name=model_info["name"],
        token_id=model_info["token_id"],
        benchmark_metric=model_info["metric"],
        benchmark_value=model_info["value"]
    )
```

### Model Validation

Validate models before registration:

```python
# Validate token metadata
is_valid = registry.validate_hokusai_tags({
    "hokusai_token_id": "TEST-001",
    "benchmark_metric": "accuracy",
    "benchmark_value": "0.95"
})

if not is_valid:
    print("Invalid metadata - check requirements")
```

## Best Practices

### 1. Consistent Metric Names

Use standardized metric names across your models:

```python
STANDARD_METRICS = {
    "classification": ["accuracy", "f1_score", "precision", "recall"],
    "regression": ["rmse", "mae", "r2_score"],
    "nlp": ["perplexity", "bleu_score", "rouge_score"],
    "ranking": ["ndcg", "map", "mrr"]
}
```

### 2. Comprehensive Tagging

Always include relevant metadata:

```python
tags = {
    # Required by Hokusai
    "hokusai_token_id": "MODEL-001",
    "benchmark_metric": "accuracy",
    "benchmark_value": "0.92",
    
    # Recommended additions
    "dataset_version": "v2.1",
    "preprocessing": "standard_scaler",
    "feature_count": "150",
    "training_samples": "10000",
    "test_samples": "2000",
    "contributor_address": contributor_eth_address,
    "contribution_hash": data_hash
}
```

### 3. Version Management

Use semantic versioning in your tags:

```python
tags = {
    "major_version": "2",    # Breaking changes
    "minor_version": "1",    # New features
    "patch_version": "3",    # Bug fixes
    "full_version": "2.1.3"
}
```

## Error Handling

Common errors and solutions:

```python
try:
    model = registry.register_tokenized_model(...)
except ValueError as e:
    if "Token ID format invalid" in str(e):
        # Fix token ID format
        token_id = token_id.upper().replace("_", "-")
    elif "Benchmark value must be numeric" in str(e):
        # Convert to float
        benchmark_value = str(float(benchmark_value))
except Exception as e:
    print(f"Registration failed: {e}")
```

## API Reference

### Core Methods

#### `register_tokenized_model()`
```python
def register_tokenized_model(
    model_uri: str,
    name: str,
    token_id: str,
    benchmark_metric: str,
    benchmark_value: str,
    tags: Optional[Dict[str, str]] = None
) -> RegisteredModel
```

#### `get_tokenized_model()`
```python
def get_tokenized_model(
    name: str,
    version: Optional[str] = None
) -> ModelVersion
```

#### `list_models_by_token()`
```python
def list_models_by_token(
    token_id: str
) -> List[ModelVersion]
```

## Related Topics

- [DeltaOne Detection](./deltaone-detection.md) - Automatic improvement detection
- [Model Versioning](./model-versioning.md) - Version management strategies
- [A/B Testing](./ab-testing.md) - Compare model versions in production