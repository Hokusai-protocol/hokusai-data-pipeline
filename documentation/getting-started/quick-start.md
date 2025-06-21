---
title: Quick Start Guide
id: quick-start
sidebar_label: Quick Start
sidebar_position: 2
---

# Quick Start Guide

## Overview

Get the Hokusai pipeline running in under 5 minutes. This guide assumes you've completed the [installation](./installation.md).

## Running Your First Pipeline

### Step 1: Activate Environment

```bash
cd hokusai-data-pipeline
source venv/bin/activate
```

### Step 2: Run in Dry-Run Mode

The fastest way to see the pipeline in action is using dry-run mode with mock data:

```bash
python -m src.pipeline.hokusai_pipeline run \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv \
    --output-dir=./outputs
```

This command:
- Uses mock models and data
- Completes in ~7 seconds
- Generates real output files
- Requires no external dependencies

### Step 3: View Results

Check the generated output:

```bash
# View the attestation-ready output
cat outputs/delta_output_*.json | jq '.'

# Check MLFlow tracking
mlflow ui
# Open http://localhost:5000 in your browser
```

## Understanding the Output

The pipeline generates a comprehensive JSON output:

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
    }
  },
  "contributor_attribution": {
    "contributor_id": "contributor_xyz789",
    "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
    "contributed_samples": 100
  }
}
```

## Running with Real Data

### Prepare Your Data

Create a CSV file with your contributed data:

```csv
query_id,query,relevant_doc_id,label
q001,"What is machine learning?",doc123,1
q002,"How to train a model?",doc456,1
q003,"Python programming basics",doc789,0
```

### Run the Pipeline

```bash
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=path/to/your/data.csv \
    --baseline-model-path=path/to/baseline/model \
    --output-dir=./outputs
```

## Pipeline Parameters

### Required Parameters
- `--contributed-data`: Path to your contribution data (CSV, JSON, or Parquet)

### Optional Parameters
- `--dry-run`: Use mock data and models
- `--output-dir`: Where to save results (default: ./outputs)
- `--baseline-model-path`: Path to baseline model
- `--random-seed`: For reproducibility (default: 42)
- `--sample-size`: Limit data samples for testing

## Monitoring Pipeline Execution

### Real-time Logs

```bash
# Set debug logging
export PIPELINE_LOG_LEVEL=DEBUG

# Run with detailed output
python -m src.pipeline.hokusai_pipeline run \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv
```

### MLFlow Dashboard

1. Start MLFlow UI:
```bash
mlflow ui
```

2. Navigate to http://localhost:5000

3. View:
   - Pipeline runs
   - Metrics comparison
   - Model artifacts
   - Parameter tracking

## Common Use Cases

### 1. Testing Data Quality

```bash
# Run with small sample to test data format
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=your_data.csv \
    --sample-size=100 \
    --dry-run
```

### 2. Comparing Model Performance

```bash
# Run with different baseline models
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=data.csv \
    --baseline-model-path=models/v1/model.pkl

python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=data.csv \
    --baseline-model-path=models/v2/model.pkl
```

### 3. Generating Attestation Proofs

```bash
# Full pipeline with ZK output
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=verified_data.csv \
    --enable-attestation \
    --output-dir=./attestations
```

## Troubleshooting Quick Start Issues

### Pipeline Fails Immediately

Check Python path:
```bash
export PYTHONPATH=.
python -m src.pipeline.hokusai_pipeline run --dry-run
```

### Import Errors

Ensure virtual environment is activated:
```bash
which python
# Should show: /path/to/project/venv/bin/python
```

### No Output Generated

Check output directory permissions:
```bash
mkdir -p outputs
chmod 755 outputs
```

## Next Steps

Now that you've run your first pipeline:

1. **[Data Contribution Guide](../data-contribution/overview.md)** - Learn about data formats and requirements
2. **[Pipeline Configuration](./configuration.md)** - Customize pipeline behavior
3. **[Architecture Deep Dive](../architecture/overview.md)** - Understand how it works
4. **[API Reference](../api-reference/index.md)** - Integrate with your systems

## Getting Help

- Check [FAQ](../troubleshooting/faq.md)
- Join [Discord](https://discord.gg/hokusai)
- File [GitHub Issues](https://github.com/hokusai/hokusai-data-pipeline/issues)