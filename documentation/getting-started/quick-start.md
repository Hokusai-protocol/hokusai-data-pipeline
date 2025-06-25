---
title: Quick Start Guide
id: quick-start
sidebar_label: Quick Start
sidebar_position: 2
---

# Quick Start Guide

Get up and running with the Hokusai data pipeline in 5 minutes. This guide assumes you've already [installed](./installation.md) the pipeline.

## 5-Minute Example

### Step 1: Activate Environment

```bash
# Navigate to project directory
cd hokusai-data-pipeline

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

### Step 2: Run Pipeline in Dry-Run Mode

```bash
# Run with mock data to test setup
python -m src.pipeline.hokusai_pipeline run \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv \
    --output-dir=./quick-start-output
```

This command:
- Uses `--dry-run` to generate mock baseline models
- Processes the test dataset
- Outputs attestation-ready results

### Step 3: View Results

```bash
# Check output
ls -la quick-start-output/

# View the attestation output
cat quick-start-output/deltaone_output_*.json | jq '.'
```

Expected output structure:
```json
{
  "pipeline_version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00Z",
  "baseline_model": {
    "id": "baseline_model_v1",
    "metrics": {
      "accuracy": 0.85,
      "f1_score": 0.82
    }
  },
  "improved_model": {
    "id": "improved_model_v1",
    "metrics": {
      "accuracy": 0.88,
      "f1_score": 0.86
    }
  },
  "delta": {
    "accuracy": 0.03,
    "f1_score": 0.04
  },
  "contributors": [{
    "id": "contributor_001",
    "wallet_address": "0x1234...5678",
    "contribution_weight": 1.0
  }]
}
```

### Step 4: View MLFlow UI (Optional)

```bash
# Start MLFlow UI
mlflow ui

# Open browser to http://localhost:5000
```

You'll see:
- Experiment runs
- Model parameters
- Performance metrics
- Artifacts

## Understanding the Pipeline

### What Just Happened?

1. **Data Loading**: The pipeline loaded your contributed data
2. **Model Training**: A new model was trained with the data
3. **Evaluation**: Both models were evaluated on a benchmark
4. **Delta Calculation**: Performance improvement was calculated
5. **Attestation**: Results were formatted for ZK-proof generation

### Pipeline Flow Diagram

```mermaid
graph LR
    A[Contributed Data] --> B[Data Validation]
    B --> C[Model Training]
    C --> D[Evaluation]
    D --> E[Delta Calculation]
    E --> F[Attestation Output]
    
    style A fill:#e1f5fe
    style F fill:#c8e6c9
```

## Real Data Example

### Prepare Your Data

Create a CSV file with your training data:

```csv
query,document,relevance
"What is machine learning?","Machine learning is a subset of AI...",1
"How does Python work?","Python is an interpreted language...",1
"What is the weather?","Machine learning algorithms can...",0
```

Save as `my_data.csv`.

### Run Pipeline with Real Data

```bash
# Set environment for real run
export HOKUSAI_TEST_MODE=false

# Run pipeline
python -m src.pipeline.hokusai_pipeline run \
    --baseline-model-path=models/baseline.pkl \
    --contributed-data=my_data.csv \
    --output-dir=./outputs \
    --contributor-address=0xYourWalletAddress \
    --experiment-name=my-first-contribution
```

### Monitor Progress

```bash
# Watch logs
tail -f outputs/pipeline.log

# Check pipeline status
python -m metaflow tag list
```

## Common Commands

### Data Validation

```bash
# Validate your data before submission
python -m src.cli.validate_data \
    --input-file=my_data.csv \
    --schema=config/data_schema.json
```

### Preview Mode

```bash
# Preview expected improvement
python -m src.preview.preview_improvement \
    --baseline-model=models/baseline.pkl \
    --contributed-data=my_data.csv
```

### Configuration Options

```bash
# Custom configuration
python -m src.pipeline.hokusai_pipeline run \
    --config=my_config.yaml \
    --batch-size=64 \
    --epochs=20 \
    --learning-rate=0.001
```

## Output Files

After a successful run, you'll find:

```
outputs/
├── deltaone_output_20240115_103000.json  # Main attestation file
├── metrics_summary.csv                    # Detailed metrics
├── model_artifacts/                       # Trained models
│   ├── baseline_model.pkl
│   └── improved_model.pkl
├── evaluation_results/                    # Evaluation details
│   └── benchmark_scores.json
└── pipeline.log                          # Execution logs
```

## Next Steps

Now that you've run your first pipeline:

1. **Submit Real Data**: See [First Contribution](./first-contribution.md)
2. **Configure Pipeline**: Check [Configuration Guide](../data-pipeline/configuration.md)
3. **Integrate with Your App**: Read [API Reference](../developer-guide/api-reference.md)
4. **Deploy to Production**: Follow [Production Guide](../tutorials/production-deployment.md)

## Troubleshooting Quick Start

### Pipeline Fails Immediately
```bash
# Check Python environment
which python  # Should show venv path

# Reinstall dependencies
pip install -r requirements.txt
```

### No Output Generated
```bash
# Check logs
cat outputs/pipeline.log | grep ERROR

# Verify data format
python -m src.cli.validate_data --input-file=your_data.csv
```

### MLFlow UI Not Working
```bash
# Kill existing process
pkill -f "mlflow ui"

# Start with specific settings
mlflow ui --backend-store-uri ./mlruns --port 5001
```

## Learn More

- **Architecture**: [System Architecture](../overview/architecture.md)
- **Data Formats**: [Data Requirements](../data-pipeline/data-formats.md)
- **Tutorials**: [Step-by-Step Tutorials](../tutorials/basic-workflow.md)
- **Support**: [Get Help](https://discord.gg/hokusai)