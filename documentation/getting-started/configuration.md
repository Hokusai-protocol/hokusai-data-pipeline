---
title: Configuration Reference
id: configuration
sidebar_label: Configuration
sidebar_position: 3
---

# Configuration Reference

## Overview

The Hokusai pipeline supports extensive configuration through environment variables, command-line arguments, and configuration files. This guide covers all configuration options.

## Environment Variables

### Core Pipeline Settings

#### HOKUSAI_TEST_MODE
- **Type**: Boolean
- **Default**: `false`
- **Description**: Enables test mode with mock data and models
- **Example**: `export HOKUSAI_TEST_MODE=true`

#### PIPELINE_LOG_LEVEL
- **Type**: String
- **Default**: `INFO`
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Description**: Controls logging verbosity
- **Example**: `export PIPELINE_LOG_LEVEL=DEBUG`

#### RANDOM_SEED
- **Type**: Integer
- **Default**: `42`
- **Description**: Ensures reproducible results
- **Example**: `export RANDOM_SEED=12345`

### MLFlow Configuration

#### MLFLOW_TRACKING_URI
- **Type**: String
- **Default**: `file:./mlruns`
- **Description**: Location for MLFlow tracking data
- **Examples**:
  ```bash
  # Local file storage
  export MLFLOW_TRACKING_URI=file:./mlruns
  
  # Remote server
  export MLFLOW_TRACKING_URI=http://mlflow-server:5000
  
  # S3 storage
  export MLFLOW_TRACKING_URI=s3://bucket/path
  ```

#### MLFLOW_EXPERIMENT_NAME
- **Type**: String
- **Default**: `hokusai-pipeline`
- **Description**: Name for MLFlow experiment tracking
- **Example**: `export MLFLOW_EXPERIMENT_NAME=production-runs`

#### MLFLOW_ARTIFACT_ROOT
- **Type**: String
- **Default**: Uses tracking URI location
- **Description**: Storage location for model artifacts
- **Example**: `export MLFLOW_ARTIFACT_ROOT=s3://models/artifacts`

### Data Processing Settings

#### MAX_SAMPLE_SIZE
- **Type**: Integer
- **Default**: `100000`
- **Description**: Maximum samples for stratified sampling
- **Example**: `export MAX_SAMPLE_SIZE=50000`

#### ENABLE_PII_DETECTION
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable automatic PII detection and hashing
- **Example**: `export ENABLE_PII_DETECTION=false`

#### DATA_VALIDATION_STRICT
- **Type**: Boolean
- **Default**: `false`
- **Description**: Fail on any data validation warning
- **Example**: `export DATA_VALIDATION_STRICT=true`

### Performance Tuning

#### PARALLEL_WORKERS
- **Type**: Integer
- **Default**: CPU count
- **Description**: Number of parallel processing workers
- **Example**: `export PARALLEL_WORKERS=8`

#### BATCH_SIZE
- **Type**: Integer
- **Default**: `1000`
- **Description**: Batch size for data processing
- **Example**: `export BATCH_SIZE=5000`

#### MEMORY_LIMIT_GB
- **Type**: Float
- **Default**: System dependent
- **Description**: Maximum memory usage in gigabytes
- **Example**: `export MEMORY_LIMIT_GB=16.0`

## Command-Line Arguments

### Required Arguments

#### --contributed-data
- **Type**: Path
- **Description**: Path to contributed data file
- **Formats**: CSV, JSON, Parquet
- **Example**: `--contributed-data=data/contributions.csv`

### Optional Arguments

#### --dry-run
- **Type**: Flag
- **Description**: Run with mock data and models
- **Example**: `--dry-run`

#### --output-dir
- **Type**: Path
- **Default**: `./outputs`
- **Description**: Directory for output files
- **Example**: `--output-dir=/tmp/pipeline-outputs`

#### --baseline-model-path
- **Type**: Path
- **Description**: Path to baseline model file
- **Example**: `--baseline-model-path=models/baseline.pkl`

#### --sample-size
- **Type**: Integer
- **Description**: Limit data to N samples
- **Example**: `--sample-size=1000`

#### --config-file
- **Type**: Path
- **Description**: Path to JSON configuration file
- **Example**: `--config-file=config/production.json`

## Configuration Files

### JSON Configuration Format

Create a configuration file to override defaults:

```json
{
  "pipeline": {
    "random_seed": 42,
    "log_level": "INFO",
    "enable_attestation": true
  },
  "data": {
    "validation_strict": true,
    "enable_pii_detection": true,
    "deduplication_columns": ["query_id", "doc_id"]
  },
  "model": {
    "training_params": {
      "learning_rate": 0.01,
      "n_estimators": 100,
      "max_depth": 10
    }
  },
  "mlflow": {
    "experiment_name": "production",
    "tags": {
      "team": "ml-ops",
      "environment": "prod"
    }
  }
}
```

### Loading Configuration

```bash
# Using config file
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=data.csv \
    --config-file=config/production.json

# Override specific values
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=data.csv \
    --config-file=config/base.json \
    --sample-size=5000
```

## Configuration Precedence

Configuration values are loaded in this order (later overrides earlier):

1. Default values in code
2. Configuration file (`--config-file`)
3. Environment variables
4. Command-line arguments

Example:
```bash
# config.json sets sample_size=10000
# Environment sets SAMPLE_SIZE=5000
# Command line sets --sample-size=1000
# Final value: 1000 (command line wins)
```

## Common Configuration Patterns

### Development Configuration

```bash
# .env.development
HOKUSAI_TEST_MODE=true
PIPELINE_LOG_LEVEL=DEBUG
MLFLOW_EXPERIMENT_NAME=dev-experiments
SAMPLE_SIZE=1000
DATA_VALIDATION_STRICT=false
```

### Production Configuration

```bash
# .env.production
HOKUSAI_TEST_MODE=false
PIPELINE_LOG_LEVEL=INFO
MLFLOW_TRACKING_URI=http://mlflow.internal:5000
MLFLOW_ARTIFACT_ROOT=s3://hokusai-models/artifacts
DATA_VALIDATION_STRICT=true
ENABLE_ATTESTATION=true
```

### CI/CD Configuration

```bash
# .env.ci
HOKUSAI_TEST_MODE=true
PIPELINE_LOG_LEVEL=WARNING
RANDOM_SEED=42
PARALLEL_WORKERS=2
MEMORY_LIMIT_GB=4.0
```

## Advanced Configuration

### Custom Model Parameters

```json
{
  "model": {
    "type": "custom_classifier",
    "params": {
      "architecture": "transformer",
      "layers": [512, 256, 128],
      "dropout": 0.2,
      "activation": "relu"
    }
  }
}
```

### Data Processing Pipeline

```json
{
  "data": {
    "preprocessing": {
      "normalize": true,
      "remove_outliers": true,
      "outlier_threshold": 3.0
    },
    "augmentation": {
      "enabled": true,
      "techniques": ["synonym_replacement", "back_translation"]
    }
  }
}
```

### Attestation Configuration

```json
{
  "attestation": {
    "enabled": true,
    "proof_system": "groth16",
    "circuit_path": "circuits/hokusai.r1cs",
    "trusted_setup": "keys/trusted_setup.key"
  }
}
```

## Validation

### Check Configuration

```bash
# Validate configuration without running pipeline
python -m src.pipeline.hokusai_pipeline validate-config \
    --config-file=config/production.json

# Show effective configuration
python -m src.pipeline.hokusai_pipeline show-config \
    --contributed-data=data.csv \
    --dry-run
```

### Common Validation Errors

1. **Invalid JSON Format**
   ```
   Error: Invalid JSON in config file
   Solution: Validate JSON syntax using jq or jsonlint
   ```

2. **Type Mismatches**
   ```
   Error: Expected int for batch_size, got string
   Solution: Ensure correct data types in configuration
   ```

3. **Missing Required Fields**
   ```
   Error: contributed_data is required
   Solution: Provide all required parameters
   ```

## Best Practices

1. **Use Environment Files**
   ```bash
   # Load environment-specific config
   source .env.production
   python -m src.pipeline.hokusai_pipeline run ...
   ```

2. **Version Control Configuration**
   ```bash
   # Track non-sensitive configs
   git add config/base.json
   git add config/development.json
   
   # Ignore sensitive configs
   echo "config/production.json" >> .gitignore
   ```

3. **Document Custom Settings**
   ```json
   {
     "_comment": "Custom settings for experiment X",
     "model": {
       "_note": "Reduced learning rate for stability",
       "learning_rate": 0.001
     }
   }
   ```

## Next Steps

- [Architecture Overview](../architecture/overview.md) - Understand configuration impact
- [Performance Tuning](../operations/performance-tuning.md) - Optimize settings
- [Troubleshooting](../troubleshooting/common-issues.md) - Fix configuration issues