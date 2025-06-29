---
id: installation
title: Installation Guide
sidebar_label: Installation
sidebar_position: 1
---

# Installation Guide

This guide covers the installation and setup of the Hokusai ML Platform.

## Prerequisites

Before installing Hokusai ML Platform, ensure you have:

- Python 3.8 or higher
- pip package manager
- Git (for development installation)
- Docker (optional, for containerized deployment)

## Installation Methods

### 1. Install from PyPI (Recommended)

```bash
pip install hokusai-ml-platform
```

### 2. Install from GitHub

For the latest development version:

```bash
pip install git+https://github.com/hokusai-protocol/hokusai-data-pipeline.git
```

### 3. Development Installation

Clone the repository and install in editable mode:

```bash
git clone https://github.com/hokusai-protocol/hokusai-data-pipeline.git
cd hokusai-data-pipeline
pip install -e .
```

## Dependencies

The platform will automatically install required dependencies:

- `mlflow>=2.8.1` - Experiment tracking and model registry
- `metaflow>=2.10.6` - Pipeline orchestration
- `redis>=5.0.1` - Caching and session management
- `fastapi>=0.104.1` - API framework
- `pydantic>=2.5.0` - Data validation
- `pandas>=2.0.0` - Data manipulation
- `numpy>=1.24.0` - Numerical operations
- `scikit-learn>=1.3.0` - ML utilities

## Environment Setup

### 1. MLflow Configuration

Set up MLflow tracking server:

```bash
# Set tracking URI (local file store)
export MLFLOW_TRACKING_URI=file:./mlruns

# Or use a remote tracking server
export MLFLOW_TRACKING_URI=http://mlflow-server:5000
```

### 2. Redis Configuration (Optional)

If using caching features:

```bash
# Set Redis connection
export REDIS_URL=redis://localhost:6379/0
```

### 3. Hokusai Configuration

Create a `.env` file in your project root:

```env
# MLflow settings
MLFLOW_TRACKING_URI=file:./mlruns
MLFLOW_EXPERIMENT_NAME=hokusai-experiments

# Redis settings (optional)
REDIS_URL=redis://localhost:6379/0

# API settings
HOKUSAI_API_URL=http://localhost:8000
HOKUSAI_API_KEY=your-api-key

# Ethereum settings
ETH_PROVIDER_URL=https://mainnet.infura.io/v3/your-project-id
```

## Docker Installation

### Using Docker Compose

1. Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  mlflow:
    image: mlflow/mlflow:latest
    ports:
      - "5000:5000"
    volumes:
      - ./mlflow-data:/mlflow
    command: >
      mlflow server
      --backend-store-uri sqlite:///mlflow/mlflow.db
      --default-artifact-root /mlflow/artifacts
      --host 0.0.0.0

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - ./redis-data:/data

  hokusai-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MLFLOW_TRACKING_URI=http://mlflow:5000
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - mlflow
      - redis
```

2. Start services:

```bash
docker-compose up -d
```

### Using Pre-built Docker Image

```bash
docker run -p 8000:8000 \
  -e MLFLOW_TRACKING_URI=http://localhost:5000 \
  hokusai/ml-platform:latest
```

## Verification

Verify your installation:

```python
import hokusai
from hokusai.core import ModelRegistry
from hokusai.evaluation import detect_delta_one

# Check version
print(f"Hokusai ML Platform version: {hokusai.__version__}")

# Test basic functionality
registry = ModelRegistry()
print("Model Registry initialized successfully!")
```

## Common Installation Issues

### Issue: MLflow Connection Error

**Error**: `ConnectionError: Unable to connect to MLflow tracking server`

**Solution**:
```bash
# Start MLflow server
mlflow server --host 0.0.0.0 --port 5000

# Update tracking URI
export MLFLOW_TRACKING_URI=http://localhost:5000
```

### Issue: Redis Connection Failed

**Error**: `redis.exceptions.ConnectionError: Error connecting to Redis`

**Solution**:
```bash
# Start Redis server
redis-server

# Or using Docker
docker run -d -p 6379:6379 redis:7-alpine
```

### Issue: Missing Dependencies

**Error**: `ModuleNotFoundError: No module named 'package_name'`

**Solution**:
```bash
# Reinstall with all dependencies
pip install hokusai-ml-platform[all]

# Or install specific extras
pip install hokusai-ml-platform[dspy,inference]
```

## Platform-Specific Instructions

### macOS

Install system dependencies:
```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Redis
brew install redis
brew services start redis
```

### Ubuntu/Debian

```bash
# Update package list
sudo apt update

# Install Python and pip
sudo apt install python3-pip python3-dev

# Install Redis
sudo apt install redis-server
sudo systemctl start redis
```

### Windows

Using WSL2 (recommended):
```bash
# Install WSL2
wsl --install

# Follow Ubuntu instructions within WSL2
```

## Next Steps

After installation, proceed to:
- [Quickstart Guide](./quickstart.md) - Get started with your first model
- [Configuration Guide](./configuration.md) - Detailed configuration options
- [API Setup](../api-reference/setup.md) - Set up API endpoints