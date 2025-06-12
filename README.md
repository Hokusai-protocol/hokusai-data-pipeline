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
- **PII Protection**: Automatic detection and hashing of sensitive data
- **Dry Run Mode**: Test pipeline with mock data before production
- **Comprehensive Testing**: Unit and integration tests included
- **Attestation Output**: ZK-proof ready JSON format
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