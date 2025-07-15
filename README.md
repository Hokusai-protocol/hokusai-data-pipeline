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

# Set your API key (required for MLflow access)
# Option 1: Environment variable
# export HOKUSAI_API_KEY=hk_live_your_api_key_here

# Option 2: In Python using setup
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

Hokusai requires API keys for secure access to all endpoints, including MLflow. Get started:

```bash
# Create your first API key
hokusai auth create-key --name "My API Key"

# Set it as an environment variable
export HOKUSAI_API_KEY=hk_live_your_key_here

# Or configure it in Python
from hokusai import setup
setup(api_key="hk_live_your_key_here")
```

See the [Authentication Guide](./documentation/authentication.md) for details.

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

## Core Components

### 1. Model Registry Service
Track and version all your ML models with automatic performance monitoring.

```python
from hokusai.core import ModelRegistry

registry = ModelRegistry()
model_id = registry.register_baseline(
    model=your_model,
    model_type="classification",
    metadata={"dataset": "customer_data_v2"}
)
```

### 2. Performance Tracking
Automatically track improvements from contributed data.

```python
from hokusai.tracking import PerformanceTracker

tracker = PerformanceTracker()
delta, attestation = tracker.track_improvement(
    baseline_metrics={"accuracy": 0.85},
    improved_metrics={"accuracy": 0.87},
    data_contribution=contribution_metadata
)
```

### 3. DSPy Integration
Build and optimize prompt-based models with automatic tracking.

```python
from hokusai.integrations.dspy import DSPyModelWrapper

# Wrap your DSPy module
wrapper = DSPyModelWrapper(your_dspy_module)
model_id = wrapper.register_with_tracking("email_assistant_v1")
```

### 4. A/B Testing Framework
Deploy models with confidence using built-in A/B testing.

```python
from hokusai.core.ab_testing import ModelTrafficRouter

router = ModelTrafficRouter()
router.create_ab_test(
    model_a="baseline_model_v1",
    model_b="improved_model_v2", 
    traffic_split={"model_a": 0.8, "model_b": 0.2}
)
```

## CLI Tools

The platform includes comprehensive CLI tools:

```bash
# Model registration
hokusai model register \
  --token-id XRAY \
  --model-path ./model.pkl \
  --metric auroc \
  --baseline 0.82

# Create API keys
hokusai auth create-key --name "Production Key"

# List your models
hokusai model list

# Track performance
hokusai performance track --model-id abc123
```

## Architecture

The platform is built with:
- **FastAPI** for high-performance REST APIs
- **MLflow** for experiment tracking and model registry
- **PostgreSQL** for metadata storage
- **Redis** for caching and rate limiting
- **Docker** for containerization

See [Architecture Documentation](./docs/ARCHITECTURE.md) for details.

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

## Development Setup

For local development:

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e ./hokusai-ml-platform

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Run tests
pytest

# Start development server
uvicorn src.api.main:app --reload
```

## Contributing

We welcome contributions! Please see our [Contributing Guide](./CONTRIBUTING.md) for details.

Key areas for contribution:
- New model type support
- Additional metric calculations
- Integration with more ML frameworks
- Performance optimizations
- Documentation improvements

## Security

- All endpoints require API key authentication
- MLflow access is protected by the same API key system
- Rate limiting prevents abuse
- Audit logging tracks all operations

Report security issues to: security@hokus.ai

## License

Apache 2.0 - See [LICENSE](./LICENSE) for details.

## Support

- 📚 Documentation: https://docs.hokus.ai
- 💬 Discord: https://discord.gg/hokusai
- 📧 Email: support@hokus.ai
- 🐛 Issues: [GitHub Issues](https://github.com/Hokusai-protocol/hokusai-data-pipeline/issues)

---

Built with ❤️ by the Hokusai Protocol team