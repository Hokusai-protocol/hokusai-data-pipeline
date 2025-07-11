# Hokusai ML Platform

A comprehensive MLOps platform for tracking and improving machine learning model performance with blockchain-ready attestations.

## Quick Start

Choose your installation method:

### Option 1: Python Package (Recommended for Data Scientists)

```bash
# Install the Hokusai ML Platform
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

Then start using it immediately:

```python
from hokusai.core import ModelRegistry
from hokusai.tracking import ExperimentManager

# Set your API key (or use environment variable HOKUSAI_API_KEY)
from hokusai import setup
setup(api_key="hk_live_your_api_key_here")

# Connect to Hokusai
registry = ModelRegistry("http://registry.hokus.ai/mlflow")
manager = ExperimentManager(registry)

# Register your model
with manager.start_experiment("my_model"):
    model = train_your_model()
    result = registry.register_baseline(model, "classification")
    print(f"Model registered: {result['model_id']}")
```

### Option 2: Full Platform (For Local Development)

```bash
# Clone and start all services
git clone https://github.com/Hokusai-protocol/hokusai-data-pipeline.git
cd hokusai-data-pipeline
docker compose -f docker-compose.minimal.yml up -d
```

Access local services at:
- Model Registry API: http://localhost:8001
- MLflow UI: http://localhost:5001
- API Docs: http://localhost:8001/docs

## Key Features

- **Model Registry**: Track all your models in one place
- **Performance Tracking**: Measure improvements from contributed data
- **Experiment Management**: MLflow-based tracking and versioning
- **Token Integration**: Associate models with Hokusai tokens
- **REST API**: Language-agnostic integration
- **Attestations**: Blockchain-ready proof of improvements
- **API Key Authentication**: Secure access with configurable rate limits

## Authentication

Hokusai uses API keys for secure access. Get started:

```bash
# Create your first API key
hokusai auth create-key --name "My API Key"

# Set it as an environment variable
export HOKUSAI_API_KEY=hk_live_your_key_here

# Or configure it in Python
from hokusai import setup
setup(api_key="hk_live_your_key_here")
```

See the [Authentication Guide](./documentation/docs/authentication.md) for details.

## Documentation

We maintain two documentation sets for different audiences:

### For Users (Public Documentation)
📚 **[User Documentation](./documentation/README.md)** - Comprehensive guides for using Hokusai
- Installation and setup
- Tutorials and examples  
- API reference
- Best practices

**Live at**: https://docs.hokus.ai

### For Contributors (Internal Documentation)
🔧 **[Developer Documentation](./docs/README.md)** - Technical docs for contributing to Hokusai
- Architecture and design
- Development setup
- Implementation details
- Advanced configuration

See [DOCUMENTATION_MAP.md](./DOCUMENTATION_MAP.md) for details on our documentation structure.

## Production Access

The platform is deployed and accessible at:
- **Web**: http://registry.hokus.ai
- **API**: http://registry.hokus.ai/api
- **MLflow**: http://registry.hokus.ai/mlflow

## Example Usage

### Basic Model Registration

```python
from hokusai.core import ModelRegistry
from hokusai.tracking import PerformanceTracker

# Initialize
registry = ModelRegistry()
tracker = PerformanceTracker()

# Register baseline model
baseline = registry.register_baseline(
    model=your_model,
    model_type="classification",
    metadata={"accuracy": 0.85}
)

# Track improvement with new data
delta, attestation = tracker.track_improvement(
    baseline_metrics={"accuracy": 0.85},
    improved_metrics={"accuracy": 0.92},
    data_contribution={"contributor": "0x...", "samples": 1000}
)
```

### Token-Based Registration

```python
# Register model with Hokusai token
result = registry.register_tokenized_model(
    model_uri="runs:/abc123/model",
    model_name="LEAD-SCORER",
    token_id="lead-scorer",
    metric_name="conversion_rate",
    baseline_value=0.15
)
```

## Project Structure

```
hokusai-data-pipeline/
├── hokusai-ml-platform/   # Python SDK package
├── src/                   # Pipeline source code
├── docs/                  # Documentation
├── infrastructure/        # AWS deployment
├── tests/                 # Test suite
└── docker-compose.yml     # Local services
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## License

Apache License 2.0

## Support

- **Issues**: [GitHub Issues](https://github.com/hokusai/hokusai-data-pipeline/issues)
- **Discord**: [Join our community](https://discord.gg/hokusai)
- **Docs**: https://docs.hokus.ai
