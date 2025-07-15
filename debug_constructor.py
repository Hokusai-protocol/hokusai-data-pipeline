"""Debug the current constructor behavior."""

import os
from unittest.mock import MagicMock

# Set mock mode
os.environ["HOKUSAI_MOCK_MODE"] = "true"

# Set path to import from hokusai-ml-platform
import sys
sys.path.insert(0, '/Users/timothyogilvie/Dropbox/Hokusai/hokusai-data-pipeline/hokusai-ml-platform/src')

from hokusai.tracking.experiments import ExperimentManager

# Test current behavior
print("Testing current constructor behavior:")

# Test 1: registry as first positional argument
print("\n1. Testing ExperimentManager(registry):")
registry = MagicMock()
registry.tracking_uri = "http://test.mlflow.com"

try:
    manager = ExperimentManager(registry)
    print(f"  Success: experiment_name={manager.experiment_name}")
    print(f"  Success: registry={manager.registry}")
    print(f"  Success: tracking_uri={manager.tracking_uri}")
except Exception as e:
    print(f"  Error: {e}")

# Test 2: experiment_name as first positional argument
print("\n2. Testing ExperimentManager('my_experiment'):")
try:
    manager = ExperimentManager("my_experiment")
    print(f"  Success: experiment_name={manager.experiment_name}")
    print(f"  Success: registry={manager.registry}")
    print(f"  Success: tracking_uri={manager.tracking_uri}")
except Exception as e:
    print(f"  Error: {e}")

# Test 3: named registry parameter
print("\n3. Testing ExperimentManager(registry=registry):")
try:
    manager = ExperimentManager(registry=registry)
    print(f"  Success: experiment_name={manager.experiment_name}")
    print(f"  Success: registry={manager.registry}")
    print(f"  Success: tracking_uri={manager.tracking_uri}")
except Exception as e:
    print(f"  Error: {e}")

# Test 4: Both parameters
print("\n4. Testing ExperimentManager('my_experiment', registry=registry):")
try:
    manager = ExperimentManager("my_experiment", registry=registry)
    print(f"  Success: experiment_name={manager.experiment_name}")
    print(f"  Success: registry={manager.registry}")
    print(f"  Success: tracking_uri={manager.tracking_uri}")
except Exception as e:
    print(f"  Error: {e}")