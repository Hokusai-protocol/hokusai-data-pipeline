---
title: Installation Guide
id: installation
sidebar_label: Installation
sidebar_position: 1
---

# Installation Guide

## Overview

This guide walks you through installing and setting up the Hokusai data pipeline on your local machine. The pipeline is a Python-based system that uses Metaflow for orchestration and MLFlow for experiment tracking.

## System Requirements

### Minimum Requirements
- Python 3.8 or higher
- 8GB RAM
- 10GB free disk space
- Unix-based OS (macOS, Linux) or WSL on Windows

### Recommended Requirements
- Python 3.11
- 16GB RAM
- 50GB free disk space for model storage
- SSD for faster data processing

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/hokusai/hokusai-data-pipeline.git
cd hokusai-data-pipeline
```

### 2. Create Python Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### 3. Run Setup Script

The project includes a setup script that handles all dependencies:

```bash
./setup.sh
```

This script will:
- Install Python dependencies from requirements.txt
- Set up MLFlow tracking directory
- Create necessary data directories
- Validate the installation

### 4. Manual Installation (Alternative)

If you prefer manual installation or the setup script fails:

```bash
# Install dependencies
pip install -r requirements.txt

# Create necessary directories
mkdir -p data/test_fixtures
mkdir -p outputs
mkdir -p mlruns
```

## Environment Configuration

### Required Environment Variables

Create a `.env` file in the project root:

```bash
# MLFlow Configuration
MLFLOW_TRACKING_URI=file:./mlruns
MLFLOW_EXPERIMENT_NAME=hokusai-pipeline

# Pipeline Configuration
HOKUSAI_TEST_MODE=false
PIPELINE_LOG_LEVEL=INFO
RANDOM_SEED=42

# Optional: Linear API for workflow automation
LINEAR_API_KEY=your_linear_api_key_here
```

### Optional Configuration

For production environments:

```bash
# Remote MLFlow server
MLFLOW_TRACKING_URI=http://your-mlflow-server:5000

# S3 artifact storage
MLFLOW_ARTIFACT_ROOT=s3://your-bucket/artifacts

# Advanced logging
PIPELINE_LOG_LEVEL=DEBUG
```

## Verify Installation

### 1. Check Python Environment

```bash
# Verify Python version
python --version

# Verify key packages
python -c "import metaflow; print(f'Metaflow: {metaflow.__version__}')"
python -c "import mlflow; print(f'MLFlow: {mlflow.__version__}')"
```

### 2. Run Test Suite

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src
```

### 3. Test Dry-Run Mode

```bash
# Run pipeline in test mode
python -m src.pipeline.hokusai_pipeline run \
    --dry-run \
    --contributed-data=data/test_fixtures/test_queries.csv
```

## Common Installation Issues

### Issue: Permission Denied on setup.sh

```bash
# Make setup script executable
chmod +x setup.sh
```

### Issue: Python Version Mismatch

Ensure you're using Python 3.8+:
```bash
# Install Python 3.11 using pyenv
pyenv install 3.11.8
pyenv local 3.11.8
```

### Issue: Missing System Dependencies

On Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install python3-dev build-essential
```

On macOS:
```bash
# Install Xcode Command Line Tools
xcode-select --install
```

### Issue: MLFlow UI Not Starting

```bash
# Check if port 5000 is in use
lsof -i :5000

# Use alternative port
mlflow ui --port 5001
```

## Next Steps

- [Quick Start Guide](./quick-start.md) - Run your first pipeline
- [Configuration Reference](./configuration.md) - Detailed configuration options
- [Architecture Overview](../architecture/overview.md) - Understand the system design

## Support

For installation issues:
1. Check the [Troubleshooting Guide](../troubleshooting/common-issues.md)
2. Review existing [GitHub Issues](https://github.com/hokusai/hokusai-data-pipeline/issues)
3. Join our [Discord community](https://discord.gg/hokusai)