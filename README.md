# Hokusai Data Pipeline

A Metaflow-based evaluation pipeline for machine learning models that produces attestation-ready outputs for zero-knowledge proof generation.

## Overview

The Hokusai data pipeline evaluates the performance improvement of machine learning models when trained with contributed data. It provides:

- Reproducible model evaluation with fixed random seeds
- Stratified sampling for large datasets
- Comprehensive metrics calculation (accuracy, precision, recall, F1, AUROC)
- Attestation-ready outputs for blockchain integration
- Comprehensive MLFlow experiment tracking and artifact management

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

## Quick Start

```bash
# Setup environment
./setup.sh

# Run in dry-run mode
python -m metaflow run src.pipeline.hokusai_pipeline:HokusaiPipeline \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv

# Run tests
pytest

# Start MLFlow UI (optional)
mlflow ui
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
│   └── utils/             # Utilities and helpers
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
├── data/                  # Data directory
│   └── test_fixtures/    # Test data
├── tools/                 # Workflow automation tools
│   └── prompts/          # AI assistance prompts
├── requirements.txt       # Python dependencies
└── setup.sh              # Setup script
```

## Workflow Integration

This project includes workflow automation tools for:
- Linear task management integration
- Automated PRD generation
- Git branch creation
- Pull request automation

Run `node tools/workflow.js` to start the workflow.

## Contributing

1. Use the workflow automation to select tasks from Linear
2. Follow the 7-step implementation process
3. Ensure all tests pass before creating PRs
4. Update documentation as needed

## License

[License information to be added]