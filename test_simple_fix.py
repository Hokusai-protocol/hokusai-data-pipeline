#!/usr/bin/env python
"""Simple test for ExperimentManager constructor fix."""

import os
import sys
from unittest.mock import MagicMock

# Set mock mode and path
os.environ["HOKUSAI_MOCK_MODE"] = "true"
sys.path.insert(0, '/Users/timothyogilvie/Dropbox/Hokusai/hokusai-data-pipeline/hokusai-ml-platform/src')

from hokusai.tracking.experiments import ExperimentManager


def test_constructor_patterns():
    """Test that all constructor patterns work correctly."""
    
    # Create a mock registry
    registry = MagicMock()
    registry.tracking_uri = "http://test.mlflow.com"
    
    print("Testing ExperimentManager constructor patterns...")
    
    # Test 1: registry as first positional argument
    print("\n1. Testing ExperimentManager(registry)")
    manager1 = ExperimentManager(registry)
    assert manager1.tracking_uri == "http://test.mlflow.com"
    assert manager1.registry == registry
    assert manager1.experiment_name == "hokusai_model_improvements"
    print("✓ PASS")
    
    # Test 2: experiment_name as first positional argument
    print("\n2. Testing ExperimentManager('my_experiment')")
    manager2 = ExperimentManager("my_experiment")
    assert manager2.experiment_name == "my_experiment"
    assert manager2.registry is None
    assert manager2.tracking_uri == "http://registry.hokus.ai/mlflow"
    print("✓ PASS")
    
    # Test 3: registry as named parameter
    print("\n3. Testing ExperimentManager(registry=registry)")
    manager3 = ExperimentManager(registry=registry)
    assert manager3.registry == registry
    assert manager3.tracking_uri == "http://test.mlflow.com"
    assert manager3.experiment_name == "hokusai_model_improvements"
    print("✓ PASS")
    
    # Test 4: experiment_name as named parameter
    print("\n4. Testing ExperimentManager(experiment_name='my_experiment')")
    manager4 = ExperimentManager(experiment_name="my_experiment")
    assert manager4.experiment_name == "my_experiment"
    assert manager4.registry is None
    assert manager4.tracking_uri == "http://registry.hokus.ai/mlflow"
    print("✓ PASS")
    
    # Test 5: both parameters named
    print("\n5. Testing ExperimentManager(experiment_name='my_experiment', registry=registry)")
    manager5 = ExperimentManager(experiment_name="my_experiment", registry=registry)
    assert manager5.experiment_name == "my_experiment"
    assert manager5.registry == registry
    assert manager5.tracking_uri == "http://test.mlflow.com"
    print("✓ PASS")
    
    # Test 6: both parameters positional
    print("\n6. Testing ExperimentManager('my_experiment', registry=registry)")
    manager6 = ExperimentManager("my_experiment", registry=registry)
    assert manager6.experiment_name == "my_experiment"
    assert manager6.registry == registry
    assert manager6.tracking_uri == "http://test.mlflow.com"
    print("✓ PASS")
    
    # Test 7: invalid first parameter type
    print("\n7. Testing ExperimentManager(123) - should raise error")
    try:
        ExperimentManager(123)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "First parameter must be" in str(e)
        print("✓ PASS")
    
    # Test 8: mlflow_tracking_uri parameter
    print("\n8. Testing ExperimentManager(mlflow_tracking_uri='http://custom.mlflow.com')")
    manager8 = ExperimentManager(mlflow_tracking_uri="http://custom.mlflow.com")
    assert manager8.tracking_uri == "http://custom.mlflow.com"
    print("✓ PASS")
    
    # Test 9: parameter precedence
    print("\n9. Testing parameter precedence")
    manager9 = ExperimentManager(
        registry=registry,
        mlflow_tracking_uri="http://explicit.mlflow.com"
    )
    assert manager9.tracking_uri == "http://explicit.mlflow.com"
    print("✓ PASS")
    
    print("\n🎉 All tests passed! The ExperimentManager constructor fix is working correctly.")


if __name__ == "__main__":
    test_constructor_patterns()