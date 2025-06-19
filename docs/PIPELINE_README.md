# Hokusai Evaluation Pipeline

The Hokusai evaluation pipeline is a Metaflow-based system for evaluating machine learning model improvements using contributed data. It produces attestation-ready outputs suitable for zero-knowledge proof generation.

## Architecture

The pipeline consists of 7 main steps:

1. **Load Baseline Model** - Load the reference model from storage or MLflow registry
2. **Integrate Contributed Data** - Load and validate new training data
3. **Train New Model** - Train an improved model with the integrated dataset
4. **Evaluate on Benchmark** - Evaluate both models on standardized benchmarks
5. **Compare and Output Delta** - Calculate performance improvements
6. **Generate Attestation Output** - Create zk-proof ready attestation
7. **Monitor and Log** - Track metrics and log results

## Quick Start

### Prerequisites

- Python 3.8+
- Virtual environment (recommended)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd hokusai-data-pipeline

# Run setup script
chmod +x setup.sh
./setup.sh

# Or manually:
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Running the Pipeline

#### Dry Run Mode (Testing)

```bash
# Run with mock data and models
python -m metaflow run src.pipeline.hokusai_pipeline:HokusaiPipeline \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv \
    --output-dir=./outputs
```

#### Production Mode

```bash
# Run with real data and models
python -m metaflow run src.pipeline.hokusai_pipeline:HokusaiPipeline \
    --baseline-model=/path/to/baseline/model \
    --contributed-data=/path/to/contributed/data.csv \
    --output-dir=./outputs
```

### Configuration

Configuration can be set via environment variables or `.env` file:

```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings
vim .env
```

Key configuration options:

- `PIPELINE_ENV`: Environment (development/production/test)
- `PIPELINE_LOG_LEVEL`: Logging level (DEBUG/INFO/WARNING/ERROR)
- `MLFLOW_TRACKING_URI`: MLflow tracking server URI
- `RANDOM_SEED`: Random seed for reproducibility
- `DRY_RUN`: Enable test mode with mock data

## Pipeline Parameters

- `--baseline-model`: Path to baseline model (optional in dry-run)
- `--contributed-data`: Path to contributed dataset (required)
- `--output-dir`: Directory for outputs (default: ./outputs)
- `--dry-run`: Run in test mode with mock data

## Output Format

The pipeline produces an attestation JSON file with:

```json
{
  "schema_version": "1.0",
  "attestation_version": "1.0",
  "run_id": "unique_run_identifier",
  "timestamp": "2024-01-01T00:00:00Z",
  "contributor": {
    "contributor_id": "contributor_xyz789",
    "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
    "data_hash": "sha256_hash_of_contributed_data",
    "contribution_timestamp": "2024-01-01T00:00:00Z"
  },
  "models": {
    "baseline": {
      "model_id": "baseline_model_v1",
      "model_hash": "sha256_hash"
    },
    "improved": {
      "model_id": "new_model_v2",
      "model_hash": "sha256_hash"
    }
  },
  "evaluation": {
    "metrics": { ... },
    "delta_results": { ... },
    "delta_score": 0.03
  },
  "proof_data": {
    "commitment": "hash_commitment",
    "nullifier": "hash_nullifier",
    "public_inputs": { ... }
  }
}
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/unit/test_config.py -v
```

### Code Style

```bash
# Format code
black src tests

# Lint code
flake8 src tests

# Type checking
mypy src
```

### Project Structure

```
src/
├── pipeline/
│   └── hokusai_pipeline.py    # Main pipeline flow
├── modules/
│   ├── baseline_loader.py      # Model loading
│   ├── data_integration.py     # Data processing
│   ├── model_training.py       # Model training
│   └── evaluation.py           # Model evaluation
└── utils/
    ├── config.py               # Configuration
    ├── constants.py            # Constants
    ├── logging_utils.py        # Logging
    └── attestation.py          # Attestation generation
```

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure virtual environment is activated
2. **MLflow connection**: Check MLFLOW_TRACKING_URI setting
3. **Memory issues**: Reduce batch_size in configuration
4. **Data format errors**: Ensure CSV/JSON/Parquet format matches schema

### Debug Mode

Enable debug logging:

```bash
export PIPELINE_LOG_LEVEL=DEBUG
```

### Getting Help

- Check logs in `./logs/` directory
- Run with `--help` for parameter documentation
- See `tests/` for usage examples