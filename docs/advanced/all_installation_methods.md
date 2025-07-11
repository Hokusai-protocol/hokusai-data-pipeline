# All Installation Methods

This document covers every possible way to install and use the Hokusai platform.

## Python Package Installation

### From GitHub (Current)
```bash
# Latest from main branch
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform

# Specific branch or tag
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git@v1.0.0#subdirectory=hokusai-ml-platform

# With optional dependencies
pip install "git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform[gtm,pipeline]"
```

### From PyPI (Future)
```bash
pip install hokusai-ml-platform
```

### Development Installation
```bash
git clone https://github.com/Hokusai-protocol/hokusai-data-pipeline.git
cd hokusai-data-pipeline/hokusai-ml-platform
python -m venv venv
source venv/bin/activate
pip install -e ".[dev,gtm,pipeline]"
```

### Git Submodule
```bash
git submodule add https://github.com/Hokusai-protocol/hokusai-data-pipeline.git vendor/hokusai
git submodule update --init --recursive
pip install -e vendor/hokusai/hokusai-ml-platform
```

## Docker Installation

### Full Infrastructure
```bash
docker compose up -d
```

### Minimal Setup
```bash
docker compose -f docker-compose.minimal.yml up -d
```

### Pre-built Images
```bash
docker run -p 8000:8000 hokusai/ml-platform:latest
```

## Direct Pipeline Execution

### Using Metaflow
```bash
python -m src.pipeline.hokusai_pipeline run \
    --contributed-data=data.csv \
    --output-dir=./outputs
```

### With Environment Variables
```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
export HOKUSAI_TEST_MODE=true
python -m src.pipeline.hokusai_pipeline run --dry-run
```

## CLI Installation

### Main CLI
```bash
cd cli/
pip install -e .
hokusai --help
```

### Direct Script Execution
```bash
python cli/src/cli.py signatures list
```

## Project Integration

### requirements.txt
```txt
# From GitHub
git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform

# With authentication
git+https://${GITHUB_TOKEN}@github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform
```

### pyproject.toml
```toml
[project]
dependencies = [
    "hokusai-ml-platform @ git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform",
]
```

### setup.py
```python
setup(
    install_requires=[
        "hokusai-ml-platform @ git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform",
    ]
)
```

## Platform-Specific Notes

### macOS
```bash
brew install python@3.8 redis
brew services start redis
```

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install python3-pip python3-dev redis-server
sudo systemctl start redis
```

### Windows (WSL2)
```bash
wsl --install
# Then follow Ubuntu instructions
```

## Private Repository Access

### Using Personal Access Token
```bash
export GITHUB_TOKEN=your_token_here
pip install git+https://${GITHUB_TOKEN}@github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform
```

### Using SSH
```bash
pip install git+ssh://git@github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform
```

### Using .netrc
```bash
echo "machine github.com login username password token" >> ~/.netrc
chmod 600 ~/.netrc
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform
```

## Verification

After installation, verify with:

```python
from hokusai.core import ModelRegistry
print("Hokusai installed successfully!")
```