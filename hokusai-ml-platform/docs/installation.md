# Installation Guide

This guide covers various methods to install the hokusai-ml-platform package.

## Quick Start

### Install from PyPI (Coming Soon)

Once published to PyPI, you can install the package using pip:

```bash
pip install hokusai-ml-platform
```

### Install from GitHub

Install the latest version directly from GitHub:

```bash
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

Install a specific version or branch:

```bash
# Install from a specific branch
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform

# Install from a specific tag/release
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git@v1.0.0#subdirectory=hokusai-ml-platform
```

### Install for Development

For development work, clone the repository and install in editable mode:

```bash
# Clone the repository
git clone https://github.com/Hokusai-protocol/hokusai-data-pipeline.git
cd hokusai-data-pipeline/hokusai-ml-platform

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

## Installation Methods

### Method 1: Using requirements.txt

Add to your `requirements.txt`:

```txt
# From PyPI (when available)
hokusai-ml-platform>=1.0.0

# From GitHub
git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform

# For private repositories with authentication
git+https://${GITHUB_TOKEN}@github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform
```

Then install:

```bash
pip install -r requirements.txt
```

### Method 2: Using pyproject.toml

Add to your project's `pyproject.toml`:

```toml
[project]
dependencies = [
    "hokusai-ml-platform @ git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform",
]
```

### Method 3: Git Submodule (for tight integration)

For projects that need close integration:

```bash
# Add as a submodule
git submodule add https://github.com/Hokusai-protocol/hokusai-data-pipeline.git vendor/hokusai
git submodule update --init --recursive

# Install from submodule
pip install -e vendor/hokusai/hokusai-ml-platform
```

## Optional Dependencies

The package includes optional dependency groups:

```bash
# Install with GTM support
pip install "hokusai-ml-platform[gtm]"

# Install with pipeline support
pip install "hokusai-ml-platform[pipeline]"

# Install all optional dependencies
pip install "hokusai-ml-platform[gtm,pipeline]"
```

## Private Repository Installation

### Using GitHub Personal Access Token

1. Create a GitHub Personal Access Token with `repo` scope
2. Set it as an environment variable:

```bash
export GITHUB_TOKEN=your_token_here
```

3. Install using the token:

```bash
pip install git+https://${GITHUB_TOKEN}@github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform
```

### Using SSH Keys

If you have SSH keys configured:

```bash
pip install git+ssh://git@github.com/Hokusai-protocol/hokusai-data-pipeline.git@main#subdirectory=hokusai-ml-platform
```

## Troubleshooting

### Common Issues

1. **Import Error: No module named 'hokusai'**
   - Ensure the package is installed: `pip list | grep hokusai`
   - Check you're in the correct virtual environment

2. **Build Dependencies Missing**
   - Install build tools: `pip install --upgrade pip setuptools wheel`

3. **Git Submodule Issues**
   - Update submodules: `git submodule update --init --recursive`

4. **Permission Denied (Private Repos)**
   - Check your GitHub token has correct permissions
   - Verify SSH keys are properly configured

### Verify Installation

After installation, verify it works:

```python
import hokusai
print(hokusai.__version__)

from hokusai.core import ModelRegistry
from hokusai.tracking import ExperimentManager
print("Installation successful!")
```

## Migration from Local Development

If you've been using the package locally, migrate to the installed version:

1. Remove any local path imports
2. Uninstall local development version: `pip uninstall hokusai-ml-platform`
3. Install using one of the methods above
4. Update imports in your code (should remain the same)

## Next Steps

- Check out the [Quick Start Guide](../README.md#quick-start) for usage examples
- View the [API Documentation](https://docs.hokus.ai) for detailed reference
- See [examples/](../examples/) for complete working examples