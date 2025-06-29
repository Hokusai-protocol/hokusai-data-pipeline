# Hokusai Data Pipeline

A comprehensive MLOps platform with Metaflow-based evaluation pipeline for machine learning models that produces attestation-ready outputs for zero-knowledge proof generation.

## Overview

The Hokusai platform provides a complete MLOps solution for evaluating the performance improvement of machine learning models when trained with contributed data. It includes:

**Core Pipeline Features:**
- Reproducible model evaluation with fixed random seeds
- Stratified sampling for large datasets
- Comprehensive metrics calculation (accuracy, precision, recall, F1, AUROC)
- Attestation-ready outputs for blockchain integration
- Comprehensive MLFlow experiment tracking and artifact management

**MLOps Platform Services:**
- Centralized model registry with versioning and lineage tracking
- Performance tracking with attestation generation
- Experiment orchestration for model comparisons
- RESTful API for programmatic access
- Docker-based infrastructure with monitoring

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Baseline Model  │────▶│  Evaluate on     │────▶│ Compare Models  │
└─────────────────┘     │  Benchmark       │     │ Calculate Delta │
                        └──────────────────┘     └─────────────────┘
                                ▲                         │
┌─────────────────┐             │                         ▼
│ Contributed     │     ┌──────────────────┐     ┌─────────────────┐
│ Data            │────▶│ Train New Model  │     │ Generate        │
└─────────────────┘     └──────────────────┘     │ Attestation     │
                                                 └─────────────────┘
```

## Features

- **Modular Design**: Each pipeline step is independently testable
- **Multiple Data Formats**: Supports CSV, JSON, and Parquet inputs
- **Data Integration**: Robust contributed data loading, validation, and merging
- **PII Protection**: Automatic detection and hashing of sensitive data
- **Data Quality**: Deduplication, schema validation, and quality scoring
- **Dry Run Mode**: Test pipeline with mock data before production
- **Comprehensive Testing**: Unit and integration tests included
- **Attestation Output**: ZK-proof ready JSON format with data provenance
- **MLFlow Integration**: Automatic experiment tracking, parameter logging, and artifact storage
- **DSPy Model Support**: Load and manage DSPy (Declarative Self-Prompting) programs

## Quick Start

### Installing the Hokusai ML Platform Package

```bash
# Install directly from GitHub
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform

# Or install from the local repository for development
pip install -e ./hokusai-ml-platform
```

### Running the MLOps Platform

```bash
# Start all services using Docker Compose
docker compose up -d

# Or use the minimal configuration (without monitoring)
docker compose -f docker-compose.minimal.yml up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f
```

### Accessing Services

Once the platform is running, you can access:

- **Model Registry API**: http://localhost:8001
  - API Documentation: http://localhost:8001/docs
  - OpenAPI Schema: http://localhost:8001/openapi.json
  
- **MLFlow UI**: http://localhost:5001
  - Track experiments, models, and metrics
  - View model lineage and versioning
  
- **MinIO Console**: http://localhost:9001
  - Username: `minioadmin`
  - Password: `minioadmin123`
  - S3-compatible artifact storage
  
- **PostgreSQL Database**: localhost:5432
  - Database: `mlflow_db`
  - Username: `mlflow`
  - Password: `mlflow_password`

### Running the Pipeline

```bash
# Setup Python environment
./setup.sh

# Run in dry-run mode
python -m metaflow run src.pipeline.hokusai_pipeline:HokusaiPipeline \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv

# Run tests
pytest
```

## Dry-Run and Test Mode

The pipeline supports dry-run mode for testing and development without requiring real data or models. This mode generates mock data and models to validate pipeline logic and performance.

### Running in Dry-Run Mode

#### Command Line
```bash
# Run with --dry-run flag
PYTHONPATH=. python -m src.pipeline.hokusai_pipeline run \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv \
    --output-dir=./outputs
```

#### Environment Variable
```bash
# Set environment variable
export HOKUSAI_TEST_MODE=true

# Run pipeline (will automatically use test mode)
PYTHONPATH=. python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=data/test_fixtures/test_queries.csv
```

### What Happens in Dry-Run Mode

1. **Mock Baseline Model**: Creates a synthetic baseline model with realistic performance metrics
2. **Mock Data Generation**: Generates deterministic mock datasets that match the expected schema
3. **Simulated Training**: Performs mock model training with plausible performance improvements
4. **Real Evaluation Logic**: Runs actual evaluation and delta computation logic with mock data
5. **Complete Output**: Generates real DeltaOne JSON and attestation outputs

### Mock Data Characteristics

- **Deterministic**: Uses fixed random seeds for reproducible results
- **Realistic Schema**: Matches expected data format with proper columns and types
- **Configurable Size**: Generates appropriate dataset sizes for testing
- **Edge Cases**: Includes various scenarios to test pipeline robustness

### Performance Requirements

- **Fast Execution**: Complete pipeline runs in under 2 minutes (typically ~7 seconds)
- **Full Coverage**: All pipeline steps execute successfully
- **Valid Outputs**: Generates properly formatted JSON outputs that match production schema

### Mock Output Example

The dry-run mode generates realistic outputs:

```json
{
  "schema_version": "1.0",
  "delta_computation": {
    "delta_one_score": 0.0332,
    "metric_deltas": {
      "accuracy": {
        "baseline_value": 0.8545,
        "new_value": 0.8840,
        "absolute_delta": 0.0296,
        "relative_delta": 0.0346,
        "improvement": true
      }
    },
    "improved_metrics": ["accuracy", "precision", "recall", "f1", "auroc"],
    "degraded_metrics": []
  },
  "pipeline_metadata": {
    "dry_run": true,
    "run_id": "1749778320931703",
    "timestamp": "2025-06-13T01:32:07.220133"
  }
}
```

### Troubleshooting Test Mode

#### Common Issues

1. **MLflow Connection**: If MLflow fails, check that the tracking URI is accessible
2. **File Permissions**: Ensure output directory is writable
3. **Module Import**: Use `PYTHONPATH=.` when running from project root
4. **Memory Issues**: Mock data is lightweight and shouldn't cause memory problems

#### Debug Mode
```bash
# Enable verbose logging
export PIPELINE_LOG_LEVEL=DEBUG

# Run with debug output
PYTHONPATH=. python -m src.pipeline.hokusai_pipeline run --dry-run --contributed-data=data/test_fixtures/test_queries.csv
```

#### Environment Variables for Test Mode

- `HOKUSAI_TEST_MODE=true`: Enable test mode
- `PIPELINE_LOG_LEVEL=DEBUG`: Enable debug logging
- `RANDOM_SEED=42`: Set deterministic random seed (default)
- `MLFLOW_EXPERIMENT_NAME=test-experiment`: Use separate experiment for testing

## MLFlow Integration

The pipeline includes comprehensive MLFlow experiment tracking:

- **Automatic Tracking**: All pipeline steps log parameters, metrics, and artifacts
- **Model Versioning**: Baseline and trained models are tracked with full metadata
- **Data Lineage**: Dataset hashes and transformations are logged for reproducibility
- **Performance Metrics**: Model evaluation results and timing data are captured
- **Artifact Storage**: Models, datasets, and outputs are stored as MLFlow artifacts

### Environment Variables

Configure MLFlow tracking with these environment variables:

```bash
# MLFlow tracking server (defaults to local file storage)
export MLFLOW_TRACKING_URI="http://localhost:5000"

# Experiment name (defaults to hokusai-pipeline)
export MLFLOW_EXPERIMENT_NAME="hokusai-production"

# Artifact storage location
export MLFLOW_ARTIFACT_ROOT="s3://my-bucket/artifacts"
```

### Viewing MLFlow UI

To view the MLFlow tracking UI:

```bash
# Start MLFlow UI (default port 5000)
mlflow ui

# Or specify a different port
mlflow ui --port 5001
```

See [docs/PIPELINE_README.md](docs/PIPELINE_README.md) for detailed documentation.

## Data Integration

The data integration step (`integrate_contributed_data`) provides robust handling of contributed datasets:

### Supported Data Sources
- **Local Files**: CSV, JSON, and Parquet formats
- **File Validation**: Automatic format detection and encoding handling
- **Schema Validation**: Configurable column requirements and data type checking

### Data Processing Pipeline
1. **Loading**: Multi-format data loading with error handling
2. **Validation**: Schema compatibility and required field checking  
3. **Cleaning**: PII detection/hashing and duplicate removal
4. **Merging**: Multiple merge strategies (append, replace, update)
5. **Quality Assessment**: Data quality scoring and manifest generation

### Configuration Examples

```python
# Basic data integration
from src.modules.data_integration import DataIntegrator

integrator = DataIntegrator(random_seed=42)

# Load contributed data
data = integrator.load_data(
    Path("contributed_data.csv"),
    run_id="my_run",
    metaflow_run_id="flow_123"
)

# Validate schema
integrator.validate_schema(data, ["query_id", "label", "features"])

# Clean and merge data
clean_data = integrator.remove_pii(data)
deduped_data = integrator.deduplicate(clean_data)
final_data = integrator.merge_datasets(base_data, deduped_data, "append")
```

### Data Manifest
Each integration produces a comprehensive data manifest including:
- Source path and file metadata
- Data hash for integrity verification
- Row/column counts and schema information
- Data quality metrics and null value analysis
- Unique value counts per column

### Performance Considerations
- **Memory Efficiency**: Streaming processing for large datasets
- **Validation Speed**: Optimized schema checking and data type validation
- **Hash Consistency**: Deterministic data hashing for reproducibility
- **Error Recovery**: Graceful handling of malformed data

## Compare and Output Delta Step

The compare_and_output_delta step (`compare_and_output_delta`) computes the DeltaOne metric and packages results for verifier consumption:

### Delta Computation
- **Metric Comparison**: Calculates delta = new_model_metrics - baseline_model_metrics
- **Multi-Metric Support**: Handles accuracy, AUROC, F1, precision, recall metrics
- **Compatibility Validation**: Ensures metric compatibility between baseline and new models
- **Error Handling**: Graceful handling of missing or incompatible metrics

### JSON Output Schema
The step produces a comprehensive JSON output containing:

```json
{
  "schema_version": "1.0",
  "delta_computation": {
    "delta_one_score": 0.025,
    "metric_deltas": {
      "accuracy": {
        "baseline_value": 0.85,
        "new_value": 0.88,
        "absolute_delta": 0.03,
        "relative_delta": 0.035,
        "improvement": true
      }
    },
    "computation_method": "weighted_average_delta",
    "metrics_included": ["accuracy", "precision", "recall", "f1_score", "auroc"]
  },
  "baseline_model": {
    "model_id": "1.0.0",
    "model_type": "mock_baseline",
    "metrics": {...},
    "mlflow_run_id": "baseline_run_123"
  },
  "new_model": {
    "model_id": "2.0.0", 
    "model_type": "hokusai_integrated_classifier",
    "metrics": {...},
    "mlflow_run_id": "new_run_456",
    "training_metadata": {...}
  },
  "contributor_attribution": {
    "contributor_id": "contributor_xyz789",
    "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
    "data_hash": "abc123def456",
    "contributor_weights": 0.1,
    "contributed_samples": 100,
    "total_samples": 1000,
    "data_manifest": {...}
  },
  "evaluation_metadata": {
    "benchmark_dataset": {...},
    "evaluation_timestamp": "2024-01-01T00:00:00",
    "pipeline_run_id": "test_run_123"
  },
  "pipeline_metadata": {
    "run_id": "test_run_123",
    "timestamp": "2024-01-01T00:00:00",
    "config": {...}
  }
}
```

### MLFlow Integration
- **Parameter Logging**: Logs delta scores, model IDs, and contributor information
- **Metric Tracking**: Records individual metric deltas and overall DeltaOne score
- **Artifact Storage**: Saves JSON output as MLFlow artifact for downstream consumption
- **Experiment Tracking**: Full integration with pipeline experiment tracking

### Configuration Examples

```python
# The step automatically receives data from previous pipeline steps
# No manual configuration required - it processes:
# - evaluation_results from evaluate_on_benchmark step
# - data_manifest from integrate_contributed_data step
# - baseline_model and new_model from previous steps

# Output files are saved to:
# {output_dir}/delta_output_{run_id}.json
```

### Error Handling
- **Input Validation**: Validates presence of required data from previous steps
- **Metric Compatibility**: Handles cases where models have different metric sets
- **Graceful Degradation**: Continues processing with partial metric data when possible
- **Detailed Logging**: Provides clear error messages for debugging

## Project Structure

```
hokusai-data-pipeline/
├── src/                    # Source code
│   ├── pipeline/          # Main pipeline flow
│   ├── modules/           # Pipeline step implementations
│   ├── services/          # MLOps services
│   ├── api/               # REST API implementation
│   └── utils/             # Utilities and helpers
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
├── data/                  # Data directory
│   └── test_fixtures/    # Test data
├── tools/                 # Workflow automation tools
│   └── prompts/          # AI assistance prompts
├── configs/               # Configuration files
│   ├── prometheus.yml    # Prometheus monitoring config
│   └── grafana/          # Grafana dashboards
├── docker-compose.yml     # Full infrastructure setup
├── docker-compose.minimal.yml  # Minimal setup without monitoring
├── Dockerfile.api         # API service container
├── Dockerfile.mlflow      # MLFlow server container
├── requirements.txt       # Core Python dependencies
├── requirements-api.txt   # API-specific dependencies
└── setup.sh              # Setup script
```

## MLOps Platform Services

### Model Registry Service

The `HokusaiModelRegistry` service provides centralized model management with enhanced token-aware functionality:

```python
from src.services.model_registry import HokusaiModelRegistry

# Initialize registry
registry = HokusaiModelRegistry()

# Register a baseline model
baseline_result = registry.register_baseline(
    model=my_model,
    model_type="logistic_regression",
    metadata={"dataset": "benchmark_v1"}
)

# Register an improved model
improved_result = registry.register_improved_model(
    baseline_model_id="baseline_001",
    improved_model=new_model,
    contributor_address="0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
    data_contribution={"samples": 1000, "quality_score": 0.95}
)

# Get model lineage
lineage = registry.get_model_lineage("baseline_001")
```

#### Token-Aware Model Registry

The registry now supports associating models with Hokusai tokens for tracking performance benchmarks:

```python
from hokusai.core.registry import ModelRegistry

# Initialize registry
registry = ModelRegistry("http://localhost:5000")

# Register a tokenized model
result = registry.register_tokenized_model(
    model_uri="runs:/abc123def456/model",
    model_name="MSG-AI",
    token_id="msg-ai",
    metric_name="reply_rate",
    baseline_value=0.1342,
    additional_tags={
        "dataset": "customer_interactions_v2",
        "environment": "production"
    }
)

# Retrieve tokenized model
model = registry.get_tokenized_model("MSG-AI", "1")
print(f"Token: {model['token_id']}, Baseline: {model['baseline_value']}")

# List all models for a token
models = registry.list_models_by_token("msg-ai")
for m in models:
    print(f"{m['model_name']} v{m['version']}: {m['metric_name']} = {m['baseline_value']}")

# Update model tags
registry.update_model_tags("MSG-AI", "1", {
    "benchmark_value": "0.1456",  # Updated performance
    "last_evaluated": "2024-01-15"
})
```

**Token ID Requirements:**
- Lowercase letters, numbers, and hyphens only
- Maximum 64 characters
- Cannot start or end with hyphen
- Examples: `msg-ai`, `lead-scorer`, `churn-predictor-v2`

**Required Tags:**
- `hokusai_token_id`: Unique identifier for the Hokusai token
- `benchmark_metric`: Performance metric name (e.g., "reply_rate", "conversion_rate")
- `benchmark_value`: Baseline performance value (must be numeric)

### Performance Tracking Service

The `PerformanceTracker` service tracks model improvements and generates attestations:

```python
from src.services.performance_tracker import PerformanceTracker

tracker = PerformanceTracker()

# Track performance improvement
delta, attestation = tracker.track_improvement(
    baseline_metrics={"accuracy": 0.85, "f1": 0.83},
    improved_metrics={"accuracy": 0.88, "f1": 0.86},
    data_contribution={
        "contributor_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
        "data_hash": "abc123",
        "samples": 1000
    }
)
```

### Experiment Manager Service

The `ExperimentManager` service orchestrates model comparison experiments:

```python
from src.services.experiment_manager import ExperimentManager

manager = ExperimentManager()

# Create an improvement experiment
experiment_id = manager.create_improvement_experiment(
    baseline_model_id="baseline_001",
    contributor_address="0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
    data_path="/path/to/contributed_data.csv"
)

# Compare models
results = manager.compare_models(
    experiment_id=experiment_id,
    baseline_model_id="baseline_001",
    improved_model_id="improved_001"
)
```

### REST API

The platform provides a comprehensive REST API for all services:

#### Authentication
All endpoints require Bearer token authentication:
```bash
curl -H "Authorization: Bearer your-token-here" http://localhost:8001/api/v1/models
```

#### Model Management Endpoints
- `GET /api/v1/models/{model_id}/lineage` - Get model lineage and improvement history
- `POST /api/v1/models/register` - Register a new model

#### Contributor Impact Endpoints
- `GET /api/v1/contributors/{address}/impact` - Get contributor's total impact across models

#### Health Check
- `GET /health` - Service health status and dependencies

### Infrastructure

### Local Development (Docker Compose)

The platform uses Docker Compose to orchestrate multiple services:

- **PostgreSQL**: Backend database for MLFlow
- **MinIO**: S3-compatible object storage for artifacts
- **MLFlow Server**: Experiment tracking and model registry
- **Redis**: Caching and rate limiting for API
- **Prometheus**: Metrics collection (optional)
- **Grafana**: Metrics visualization (optional)
- **Model Registry API**: REST API service

### Production Deployment (AWS)

For production deployments, the platform includes complete AWS infrastructure:

- **ECS Fargate**: Containerized services with auto-scaling
- **RDS PostgreSQL**: Managed database with Multi-AZ deployment
- **S3**: Secure artifact storage with encryption
- **Application Load Balancer**: HTTPS endpoints with health checks
- **CloudWatch**: Comprehensive monitoring and alerting
- **Secrets Manager**: Secure credential storage

See [infrastructure/README.md](infrastructure/README.md) for detailed deployment instructions.

## Metric Logging Convention

The platform uses a standardized metric logging convention for consistent tracking across all components:

### Metric Categories

- **usage:** - User interaction metrics (e.g., `usage:reply_rate`, `usage:conversion_rate`)
- **model:** - Model performance metrics (e.g., `model:accuracy`, `model:f1_score`)
- **pipeline:** - Pipeline execution metrics (e.g., `pipeline:duration_seconds`, `pipeline:data_processed`)
- **custom:** - Custom metrics specific to your use case

### Usage Example

```python
from src.utils.metrics import log_model_metrics, log_pipeline_metrics, log_usage_metrics

# Log model performance metrics
log_model_metrics({
    "accuracy": 0.89,
    "f1_score": 0.87,
    "latency_ms": 15.2
})

# Log pipeline execution metrics
log_pipeline_metrics({
    "duration_seconds": 120.5,
    "data_processed": 10000,
    "success_rate": 0.98
})

# Log usage metrics
log_usage_metrics({
    "reply_rate": 0.1523,
    "conversion_rate": 0.0821
})
```

### Metric Naming Convention

- Use lowercase with underscores: `metric_name`
- Include category prefix: `category:metric_name`
- Valid pattern: `^([a-z]+:)?[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$`

### Standard Metrics Reference

See `STANDARD_METRICS` in `src/utils/metrics.py` for the full list of predefined metrics.

### Migration from Legacy Metrics

The `migrate_metric_name()` function helps convert old metric names to the new convention:

```python
from src.utils.metrics import migrate_metric_name

# Automatic migration
old_name = "accuracy"
new_name = migrate_metric_name(old_name)  # Returns "model:accuracy"
```

## DSPy Model Support

The platform now includes comprehensive support for DSPy (Declarative Self-Prompting) models:

### Loading DSPy Models

```python
from src.services.dspy_model_loader import DSPyModelLoader

# Initialize loader
loader = DSPyModelLoader()

# Load from configuration
program = loader.load_from_config("examples/dspy/basic_config.yaml")

# Load from Python class
program = loader.load_from_class("my_models.EmailAssistant", "EmailAssistant")

# Load from HuggingFace
program = loader.load_from_huggingface("hokusai/dspy-model", "model.pkl")
```

### DSPy Configuration Example

```yaml
name: email-assistant
version: 1.0.0
source:
  type: local
  path: ./models/email_assistant.py
  class_name: EmailAssistant

signatures:
  generate_email:
    inputs: [recipient, subject, context]
    outputs: [email_body]
    description: Generate professional emails
```

### Executing DSPy Programs

```python
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor

# Initialize executor
executor = DSPyPipelineExecutor()

# Execute program
result = executor.execute(
    model_id="email-assistant-v1",
    inputs={"recipient": "john@example.com", "subject": "Meeting"}
)

# Batch execution
results = executor.execute_batch(
    model_id="email-assistant-v1",
    inputs_list=[{"recipient": "john"}, {"recipient": "jane"}]
)
```

### DSPy REST API

```bash
# Execute DSPy program via API
curl -X POST http://localhost:8001/api/v1/dspy/execute \
  -H "Authorization: Bearer TOKEN" \
  -d '{"program_id": "email-assistant", "inputs": {...}}'
```

### DSPy Signature Library

The platform includes a comprehensive library of reusable DSPy signatures:

```python
from src.dspy_signatures import EmailDraft, SummarizeText, RespondToUser

# Use pre-built signatures
email_sig = EmailDraft()
summary_sig = SummarizeText()

# Browse available signatures
from src.dspy_signatures import get_global_registry
registry = get_global_registry()
print(registry.list_signatures())  # Shows 20+ available signatures
```

See documentation:
- [DSPy Model Loader](docs/DSPY_MODEL_LOADER.md) - Loading and managing DSPy models
- [DSPy Pipeline Executor](docs/DSPY_PIPELINE_EXECUTOR.md) - Executing DSPy programs
- [DSPy Signature Library](docs/DSPY_SIGNATURE_LIBRARY.md) - Pre-built signatures and customization

### Configuration

Environment variables can be set in `.env` file:

```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8001
SECRET_KEY=your-secret-key-here

# MLFlow Configuration
MLFLOW_TRACKING_URI=http://mlflow-server:5000

# Database Configuration
POSTGRES_URI=postgresql://mlflow:mlflow_password@postgres/mlflow_db

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_PERIOD=60
```

## Troubleshooting

### Installation Issues

#### License Configuration Error
If you encounter an error like `setuptools.errors.InvalidConfigError: License classifiers have been superseded by license expressions` when installing the package, this has been fixed in the latest version. Make sure you're installing from the main branch.

#### Missing Tracking Components
The `ExperimentManager` and `PerformanceTracker` components are now included in the `hokusai.tracking` module. If you encounter import errors, ensure you have the latest version installed:

```bash
# Upgrade to latest version
pip install --upgrade git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

#### Development Installation
For development work, install in editable mode with all optional dependencies:

```bash
cd hokusai-ml-platform
pip install -e ".[dev,gtm,pipeline]"
```
