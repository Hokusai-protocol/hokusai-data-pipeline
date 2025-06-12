#!/bin/bash

# Setup script for Hokusai data pipeline

echo "Setting up Hokusai data pipeline environment..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.8"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
    echo "Error: Python 3.8 or higher is required. Current version: $python_version"
    exit 1
fi

echo "Python version check passed: $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing requirements..."
pip install -r requirements.txt

# Verify Metaflow installation
echo "Verifying Metaflow installation..."
python -c "import metaflow; print(f'Metaflow version: {metaflow.__version__}')"

echo "Setup complete! To activate the environment, run: source venv/bin/activate"