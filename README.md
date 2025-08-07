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
registry = ModelRegistry("https://registry.hokus.ai/api/mlflow")
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
- **Event Messaging**: Automatic notifications when models are ready for token deployment

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

### MLflow Integration

Hokusai provides a fully integrated MLflow tracking server accessible through our API proxy. This allows you to use standard MLflow clients with your Hokusai API key:

```python
import mlflow
import os

# Configure MLflow to use Hokusai's tracking server
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_your_key_here"

# Standard MLflow operations work seamlessly
mlflow.set_experiment("my-experiment")
with mlflow.start_run():
    mlflow.log_param("model_type", "random_forest")
    mlflow.log_metric("accuracy", 0.92)
    mlflow.sklearn.log_model(model, "model")

# Use MLflow client for advanced operations
client = mlflow.tracking.MlflowClient()
models = client.search_registered_models()
```

**Note**: The MLflow UI is not directly accessible. Use the API endpoints for all operations.

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
- **Web**: https://registry.hokus.ai
- **API**: https://registry.hokus.ai/api
- **MLflow**: https://registry.hokus.ai/api/mlflow

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

## Event-Driven Model Deployment

When models are registered and meet baseline performance requirements, the platform automatically emits `model_ready_to_deploy` messages to a Redis queue. This enables:

- **Automated Token Deployment**: Downstream systems can listen for these events to trigger token minting
- **Real-time Notifications**: Get notified immediately when models are deployment-ready
- **Audit Trail**: Track all deployment-ready models through the message queue

See [Message Queue Setup Guide](./docs/message-queue-setup.md) for configuration details.

## Contributing

We welcome contributions! Please see our [Contributing Guide](./CONTRIBUTING.md) for details.

Key areas for contribution:
- New model type support
- Additional metric calculations
- Integration with more ML frameworks
- Performance optimizations
- Documentation improvements

## Recent Fixes and Improvements

The platform has undergone significant improvements to ensure reliable API connectivity:

### ✅ Resolved Issues

1. **MLflow Proxy Routing Fixed** - Resolved 404 errors when registering models by implementing proper internal service discovery
2. **Database Authentication Enhanced** - Fixed PostgreSQL connection issues with improved retry logic and fallback support
3. **Service Discovery Implemented** - Added AWS Cloud Map for internal service communication
4. **Health Check Improvements** - Enhanced monitoring with circuit breaker patterns and detailed diagnostics
5. **Artifact Storage Fixed** - Resolved S3 artifact upload/download issues for model registration

### API Endpoint Fixes

All MLflow operations are now properly proxied through the Hokusai API at `/mlflow/*`. Key improvements:

- **Fixed 404 Errors**: Model registration and artifact uploads now work reliably
- **Enhanced Path Translation**: Automatic handling of internal vs external MLflow routing  
- **Improved Error Handling**: Better error messages and debugging information
- **Circuit Breaker Protection**: Automatic recovery from temporary service disruptions

### Endpoints Available

- **MLflow API**: `/mlflow/api/2.0/mlflow/*` - All standard MLflow operations
- **MLflow Artifacts**: `/mlflow/api/2.0/mlflow-artifacts/*` - Model artifact management
- **Health Checks**: `/mlflow/health/mlflow` - Comprehensive service diagnostics
- **Model Management**: `/models/*` - Hokusai-specific model operations
- **DSPy Pipeline**: `/api/v1/dspy/*` - DSPy program execution

📖 **Complete Documentation**: 
- **[API Endpoint Reference](./docs/API_ENDPOINT_REFERENCE.md)** - Comprehensive endpoint documentation
- **[Authentication Guide](./docs/AUTHENTICATION_GUIDE.md)** - Authentication setup and requirements
- **[404 Troubleshooting Guide](./docs/404_TROUBLESHOOTING_GUIDE.md)** - Common error resolution
- **[API Migration Guide](./docs/API_MIGRATION_GUIDE.md)** - Upgrade guide for recent changes

All endpoints require Bearer token authentication using your Hokusai API key.

### Testing Health Checks

```bash
# Test locally with Docker Compose
docker-compose -f docker-compose.health-test.yml up

# Run health check test suite
python scripts/test_health_checks.py

# Manual health check
curl http://localhost:8001/health?detailed=true
```

For deployment troubleshooting, see [Deployment Troubleshooting Guide](./docs/deployment-troubleshooting.md).

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