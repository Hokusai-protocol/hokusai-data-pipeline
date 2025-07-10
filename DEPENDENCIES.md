# Dependency Management Guide

## Overview

This document explains the dependency management strategy for the Hokusai data pipeline project and how to resolve version conflicts between different components.

## Dependency Conflicts

### Numpy Version Conflict

The main dependency conflict in this project is with numpy:
- **MLflow 2.9.0** requires: `numpy<2.0` (uses numpy 1.26.4)
- **DSPy-ai 2.6.0** prefers: `numpy>=2.0` (uses numpy 2.3.1)

### PyArrow Version Conflict

Another conflict exists with pyarrow:
- **MLflow 2.9.0** requires: `pyarrow<15,>=4.0.0` (uses pyarrow 14.0.2)
- **Latest pyarrow**: 20.0.0

## Modular Requirements Structure

To manage these conflicts, we've created a modular requirements structure:

### 1. Core Dependencies (`requirements-core.in`)
Essential dependencies without ML frameworks:
- python-dotenv
- click
- pydantic
- rich
- jsonschema
- pyarrow (constrained to <15 for MLflow compatibility)
- fastparquet

### 2. MLflow Dependencies (`requirements-mlflow.in`)
MLflow and data science stack:
- mlflow==2.9.0
- metaflow==2.11.0
- numpy<2.0 (MLflow requirement)
- pandas==2.0.3
- scikit-learn==1.4.0

### 3. DSPy Dependencies (`requirements-dspy.in`)
DSPy-ai as optional dependency:
- dspy-ai>=2.6.0
- huggingface-hub>=0.19.0

### 4. Development Dependencies (`requirements-dev.in`)
Development and testing tools:
- pytest and plugins
- ruff linter
- mypy type checker
- pre-commit
- pip-tools
- mkdocs

### 5. Combined Dependencies (`requirements-all.in`)
A unified requirements file that resolves conflicts by using MLflow-compatible versions.

## Installation Strategies

### Option 1: Combined Installation (Recommended)
Use the pre-resolved combined requirements:
```bash
pip install -r requirements-all.txt
```

This uses MLflow-compatible versions throughout (numpy 1.26.4).

### Option 2: Modular Installation
Install different components in separate environments:

**For MLflow development:**
```bash
pip install -r requirements-mlflow.txt
```

**For DSPy development (separate environment):**
```bash
pip install -r requirements-core.txt
pip install -r requirements-dspy.txt
```

### Option 3: Docker-based Isolation
Use Docker containers to isolate different services with their specific dependencies.

## Generating Locked Requirements

We use pip-tools to generate locked requirements files:

```bash
# Install pip-tools
pip install pip-tools

# Compile requirements
pip-compile requirements-all.in -o requirements-all.txt
pip-compile requirements-core.in -o requirements-core.txt
pip-compile requirements-mlflow.in -o requirements-mlflow.txt
pip-compile requirements-dspy.in -o requirements-dspy.txt
pip-compile requirements-dev.in -o requirements-dev.txt
```

## Version Pinning Rationale

### Critical Versions
- **numpy==1.26.4**: Last version before 2.0, compatible with MLflow
- **pandas==2.0.3**: Compatible with both numpy 1.26.4 and MLflow
- **scikit-learn==1.4.0**: Compatible with numpy 1.26.4
- **mlflow==2.9.0**: Stable version with broad compatibility
- **pyarrow<15**: Required by MLflow 2.9.0

### Development Tools
- **ruff==0.1.8**: Pinned for consistent linting rules
- **pytest==7.4.3**: Stable version with good plugin support
- **mypy==1.7.0**: Recent version with good type checking features

## Updating Dependencies

When updating dependencies:

1. **Check compatibility**: Verify version constraints in requirements-*.in files
2. **Test modular installs**: Ensure each requirements file installs cleanly
3. **Run full test suite**: Verify all tests pass with new versions
4. **Update documentation**: Document any breaking changes

## Troubleshooting

### Common Issues

1. **Import errors with numpy**:
   - Ensure you're using the correct environment
   - Check numpy version: `python -c "import numpy; print(numpy.__version__)"`

2. **MLflow compatibility issues**:
   - MLflow 2.9.0 has strict dependency requirements
   - Consider upgrading MLflow if newer versions support numpy 2.0

3. **DSPy installation failures**:
   - DSPy has many dependencies that may conflict
   - Consider installing in a separate environment

### Future Improvements

1. **MLflow upgrade**: Monitor MLflow releases for numpy 2.0 support
2. **Dependency isolation**: Consider using poetry or pdm for better dependency resolution
3. **CI/CD testing**: Add matrix testing for different dependency combinations