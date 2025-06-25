---
title: Installation Guide
id: installation
sidebar_label: Installation
sidebar_position: 1
---

# Installation Guide

This guide covers installing and setting up the Hokusai data pipeline for local development and production use.

## Prerequisites

### System Requirements
- **Operating System**: Linux, macOS, or Windows with WSL2
- **Python**: 3.8 or higher
- **Memory**: Minimum 8GB RAM (16GB recommended)
- **Storage**: At least 10GB free space
- **Docker**: (Optional) For containerized deployment

### Required Software
```bash
# Check Python version
python --version  # Should be 3.8+

# Check pip
pip --version

# Check git
git --version
```

## Installation Methods

### Method 1: From Source (Recommended)

#### 1. Clone the Repository
```bash
git clone https://github.com/Hokusai-protocol/hokusai-data-pipeline.git
cd hokusai-data-pipeline
```

#### 2. Create Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

#### 3. Install Dependencies
```bash
# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Install development dependencies (optional)
pip install -r requirements-dev.txt
```

#### 4. Set Up Environment Variables
```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
nano .env  # or use your preferred editor
```

Required environment variables:
```bash
# MLFlow Configuration
MLFLOW_TRACKING_URI=./mlruns
MLFLOW_EXPERIMENT_NAME=hokusai-evaluation

# Pipeline Configuration
HOKUSAI_OUTPUT_DIR=./outputs
HOKUSAI_LOG_LEVEL=INFO

# Optional: For cloud storage
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
S3_BUCKET=your_bucket
```

### Method 2: Using Docker (Coming Soon)

```bash
# Pull the Docker image
docker pull hokusai/data-pipeline:latest

# Run with docker-compose
docker-compose up -d
```

### Method 3: pip Installation (Future Release)

Once the `hokusai-ml-platform` package is released:
```bash
# Install from PyPI
pip install hokusai-ml-platform

# Or install with ML extras
pip install hokusai-ml-platform[ml]
```

## Configuration

### Pipeline Configuration
Create `config/pipeline_config.yaml`:
```yaml
pipeline:
  name: hokusai-evaluation
  version: 1.0.0
  
training:
  batch_size: 32
  epochs: 10
  learning_rate: 0.001
  
evaluation:
  metrics:
    - accuracy
    - precision
    - recall
    - f1_score
    - auroc
  
output:
  format: json
  include_attestation: true
  compression: gzip
```

### Data Validation Rules
Configure in `config/validation_rules.yaml`:
```yaml
data_validation:
  required_columns:
    - query
    - document
    - relevance
  
  max_file_size_mb: 1000
  
  pii_detection:
    enabled: true
    fields_to_check:
      - query
      - document
```

## Verify Installation

### 1. Run Tests
```bash
# Run unit tests
pytest tests/unit/

# Run all tests
pytest

# Run with coverage
pytest --cov=src
```

### 2. Check CLI
```bash
# Verify CLI is working
python -m src.cli.validate_data --help

# Run pipeline help
python -m src.pipeline.hokusai_pipeline --help
```

### 3. Run Dry-Run Mode
```bash
# Test pipeline with mock data
python -m src.pipeline.hokusai_pipeline run \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv \
    --output-dir=./test_output
```

Expected output:
```
Pipeline completed successfully!
Output written to: ./test_output/deltaone_output_*.json
```

## MLFlow Setup

### 1. Start MLFlow UI (Optional)
```bash
# Start MLFlow tracking server
mlflow ui --host 0.0.0.0 --port 5000

# Access at http://localhost:5000
```

### 2. Configure MLFlow Backend
For production, configure a proper backend:
```bash
# PostgreSQL backend
export MLFLOW_TRACKING_URI=postgresql://user:password@localhost/mlflow

# S3 artifact store
export MLFLOW_ARTIFACT_ROOT=s3://bucket/mlflow-artifacts
```

## Troubleshooting

### Common Issues

#### 1. Import Errors
```bash
# Error: ModuleNotFoundError: No module named 'metaflow'
# Solution:
pip install metaflow

# Ensure you're in the virtual environment
which python  # Should show venv path
```

#### 2. Permission Errors
```bash
# Error: Permission denied when creating outputs
# Solution:
chmod +x setup.sh
sudo chown -R $USER:$USER outputs/
```

#### 3. Memory Issues
```bash
# Error: MemoryError during pipeline execution
# Solution: Set memory limits
export METAFLOW_MEMORY=8192
export METAFLOW_CPU=4
```

#### 4. MLFlow Connection Issues
```bash
# Error: Cannot connect to MLFlow
# Solution: Check tracking URI
mlflow ui --backend-store-uri ./mlruns
```

### Getting Help

If you encounter issues:

1. Check the [Troubleshooting Guide](../developer-guide/troubleshooting.md)
2. Search [GitHub Issues](https://github.com/Hokusai-protocol/hokusai-data-pipeline/issues)
3. Join our [Discord Community](https://discord.gg/hokusai)
4. Create a new issue with:
   - Error message
   - Steps to reproduce
   - Environment details (OS, Python version)
   - Relevant logs

## Next Steps

- [Quick Start Guide](./quick-start.md) - Run your first pipeline
- [First Contribution](./first-contribution.md) - Submit data for model improvement
- [Configuration Guide](../data-pipeline/configuration.md) - Advanced configuration options
- [API Reference](../developer-guide/api-reference.md) - Integrate with your applications

## Appendix: Development Setup

### For Contributors
```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Install development tools
pip install black isort flake8 mypy

# Run code formatting
black src/ tests/
isort src/ tests/

# Run linting
flake8 src/ tests/
mypy src/
```

### VS Code Configuration
`.vscode/settings.json`:
```json
{
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "python.testing.pytestEnabled": true
}
```