# Hokusai ML Platform

A comprehensive MLOps platform for model management, versioning, A/B testing, and performance tracking in the Hokusai ecosystem.

## Overview

The Hokusai ML Platform provides a unified infrastructure for managing machine learning models across different Hokusai projects. It offers:

- **Model Registry**: Centralized model storage with MLflow integration
- **Version Management**: Semantic versioning and rollback capabilities
- **A/B Testing**: Traffic routing and performance comparison
- **Inference Pipeline**: Optimized inference with caching
- **Performance Tracking**: Model improvement tracking and attestation
- **Experiment Management**: Comprehensive experiment tracking

## Installation

### Install from GitHub

```bash
# Install latest version
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform

# Install with optional dependencies
pip install "git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform[gtm]"
pip install "git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform[pipeline]"
```

### Install from PyPI

**Note**: PyPI package is coming soon. For now, please install from GitHub.

### Development Installation

```bash
# Clone the repository
git clone https://github.com/Hokusai-protocol/hokusai-data-pipeline.git
cd hokusai-data-pipeline/hokusai-ml-platform

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

For more installation options, see the [Installation Guide](docs/installation.md).

## Quick Start

### 1. Set Up Authentication

```bash
# Set your Hokusai API key as an environment variable
export HOKUSAI_API_KEY="your-api-key-here"
```

To obtain your API key:
1. Log in to https://hokus.ai
2. Navigate to Settings → API Keys
3. Click "Generate New Key"
4. Copy and save the key securely

### 2. Initialize the Platform

```python
import os
from hokusai.core import ModelRegistry, ModelVersionManager
from hokusai.core.ab_testing import ModelTrafficRouter
from hokusai.core.inference import HokusaiInferencePipeline

# Verify API key is set
if not os.getenv("HOKUSAI_API_KEY"):
    raise ValueError("Please set HOKUSAI_API_KEY environment variable")

# Initialize core components
registry = ModelRegistry(tracking_uri="https://registry.hokus.ai/api/mlflow")
version_manager = ModelVersionManager(registry)
traffic_router = ModelTrafficRouter()

# Create inference pipeline
inference_pipeline = HokusaiInferencePipeline(
    registry=registry,
    version_manager=version_manager,
    traffic_router=traffic_router
)
```

### 3. Register a Model

```python
from hokusai.core.models import ModelFactory, ModelType

# Create and register a baseline model
model = ModelFactory.create_model(
    model_type=ModelType.CLASSIFICATION,
    model_id="lead-scorer-v1",
    version="1.0.0",
    config={"n_classes": 2}
)

# Register as baseline
entry = registry.register_baseline(
    model=model,
    model_type="lead_scoring",
    metadata={
        "dataset": "initial_training_set",
        "author": "data_science_team"
    }
)
```

### 4. Track Model Improvements

```python
from hokusai.tracking import ExperimentManager, PerformanceTracker

# Initialize tracking components
experiment_manager = ExperimentManager(registry)
performance_tracker = PerformanceTracker()

# Start an experiment
with experiment_manager.start_experiment("lead_scoring_improvement"):
    # Train improved model
    improved_model = train_model(new_data)
    
    # Track performance improvement
    delta, attestation = performance_tracker.track_improvement(
        baseline_metrics={"accuracy": 0.85},
        improved_metrics={"accuracy": 0.92},
        data_contribution={"contributor": "0xABC...", "data_size": 10000}
    )
    
    # Register improved model
    registry.register_improved_model(
        model=improved_model,
        baseline_id="lead-scorer-v1",
        delta_metrics=delta,
        contributor="0xABC..."
    )
```

### 5. Run A/B Tests

```python
from hokusai.core.ab_testing import ABTestConfig

# Configure A/B test
config = ABTestConfig(
    test_id="lead-scoring-v2-test",
    model_a="lead-scorer-v1",
    model_b="lead-scorer-v2",
    traffic_split={"model_a": 0.9, "model_b": 0.1},
    duration_hours=24
)

# Start A/B test
traffic_router.create_ab_test(config)

# Route requests during inference
model_to_use = traffic_router.route_request("lead-scoring-v2-test", user_id)
```

### 6. Run Inference

```python
from hokusai.core.inference import InferenceRequest

# Create inference request
request = InferenceRequest(
    request_id="req-12345",
    model_type="lead_scoring",
    data={"features": [0.5, 0.3, 0.8]},
    user_id="user-123"
)

# Run inference (handles caching, A/B testing, etc.)
response = await inference_pipeline.predict(request)

print(f"Prediction: {response.prediction}")
print(f"Model Version: {response.model_version}")
print(f"Cache Hit: {response.cache_hit}")
print(f"Latency: {response.latency_ms}ms")
```

## Architecture

### Core Components

1. **Model Abstraction Layer** (`hokusai.core.models`)
   - Base `HokusaiModel` class for all models
   - `ModelFactory` for creating model instances
   - Support for classification, regression, and custom models

2. **Model Registry** (`hokusai.core.registry`)
   - MLflow-based model storage
   - Model lineage tracking
   - Contributor attribution

3. **Version Management** (`hokusai.core.versioning`)
   - Semantic versioning (major.minor.patch)
   - Automatic version incrementing
   - Version comparison and rollback

4. **A/B Testing** (`hokusai.core.ab_testing`)
   - Deterministic traffic routing
   - Multi-variant testing support
   - Statistical analysis of results

5. **Inference Pipeline** (`hokusai.core.inference`)
   - Redis-based caching
   - Batch prediction support
   - Automatic fallback on failures

### API Layer

The platform provides REST API endpoints via FastAPI:

```python
from hokusai.api import create_app

app = create_app()
# Run with: uvicorn app:app --reload
```

Key endpoints:
- `POST /models/register` - Register new models
- `GET /models/{model_id}/lineage` - Get model lineage
- `GET /contributors/{address}/impact` - Get contributor impact
- `POST /inference/predict` - Run inference

## Configuration

### Environment Variables

```bash
# API Configuration
HOKUSAI_API_KEY=your-api-key-here

# MLflow Configuration (automatically configured when using Hokusai API)
MLFLOW_TRACKING_URI=https://registry.hokus.ai/api/mlflow

# Redis Configuration  
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# API Configuration
API_HOST=0.0.0.0
API_PORT=8001
API_WORKERS=4
```

### Cache Configuration

```python
from hokusai.core.inference import CacheConfig

cache_config = CacheConfig(
    enabled=True,
    ttl_seconds=300,  # 5 minutes
    max_cache_size_mb=1024,  # 1GB
    eviction_policy="lru"
)
```

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=hokusai --cov-report=html

# Run specific test categories
pytest -m unit
pytest -m integration
pytest -m "not slow"
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.

## Support

- Documentation: https://docs.hokus.ai/ml-platform
- Issues: https://github.com/hokusai/hokusai-ml-platform/issues
- Discord: https://discord.gg/hokusai