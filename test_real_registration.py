#!/usr/bin/env python3
"""
Test actual model registration with proper MLFlow setup.
This reproduces and fixes the third-party registration issue.
"""

import os
import sys
import mlflow
import tempfile
import pickle
from datetime import datetime
from sklearn.linear_model import LogisticRegression
import numpy as np

def create_test_model():
    """Create a simple test model."""
    # Create dummy model
    model = LogisticRegression()
    X = np.array([[0, 0], [1, 1], [2, 2], [3, 3]])
    y = np.array([0, 0, 1, 1])
    model.fit(X, y)
    return model

def test_registration_scenario():
    """Test the exact scenario third parties face."""
    print("Third-Party Model Registration Test")
    print("=" * 70)
    
    # Scenario 1: Default SDK behavior (what fails)
    print("\nScenario 1: Default SDK Configuration")
    print("-" * 50)
    
    try:
        # Clear any MLFlow settings
        for key in list(os.environ.keys()):
            if key.startswith("MLFLOW_"):
                del os.environ[key]
        
        # Only set Hokusai API key (what third parties do)
        os.environ["HOKUSAI_API_KEY"] = "test_api_key_123"
        
        from hokusai import ModelRegistry
        registry = ModelRegistry()
        print(f"Registry tracking URI: {registry.tracking_uri}")
        
        # This will fail because api.hokus.ai doesn't exist
        result = registry.register_tokenized_model(
            model_uri="runs:/dummy/model",
            model_name="test-model",
            token_id="test",
            metric_name="accuracy",
            baseline_value=0.85
        )
        print("✓ Registration succeeded (unexpected!)")
        
    except Exception as e:
        print(f"✗ Failed as expected: {type(e).__name__}")
        print(f"  Error: {str(e)[:100]}...")
    
    # Scenario 2: With proper MLFlow configuration
    print("\n\nScenario 2: With Proper Configuration")
    print("-" * 50)
    
    try:
        # Set up for local MLFlow
        os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5001"
        os.environ["HOKUSAI_API_KEY"] = "test_api_key_123"
        
        # Create an MLFlow run first
        mlflow.set_tracking_uri("http://localhost:5001")
        
        with mlflow.start_run() as run:
            # Log a model
            model = create_test_model()
            mlflow.sklearn.log_model(model, "model")
            run_id = run.info.run_id
            print(f"Created MLFlow run: {run_id}")
        
        # Now register with Hokusai
        from hokusai import ModelRegistry
        registry = ModelRegistry(tracking_uri="http://localhost:5001")
        
        model_uri = f"runs:/{run_id}/model"
        result = registry.register_tokenized_model(
            model_uri=model_uri,
            model_name=f"test-model-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            token_id="test-token",
            metric_name="accuracy", 
            baseline_value=0.85
        )
        
        print("✓ Registration succeeded!")
        print(f"  Model: {result['model_name']}")
        print(f"  Version: {result['version']}")
        print(f"  Token: {result['token_id']}")
        
    except Exception as e:
        print(f"✗ Registration failed: {type(e).__name__}")
        print(f"  Error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Scenario 3: Using the Hokusai API endpoint
    print("\n\nScenario 3: Using Hokusai API Endpoint")
    print("-" * 50)
    
    try:
        # Point to local Hokusai API
        os.environ["HOKUSAI_API_KEY"] = "test_api_key_123"
        
        from hokusai import ModelRegistry
        registry = ModelRegistry(
            api_endpoint="http://localhost:8001",
            tracking_uri="http://localhost:5001"
        )
        
        print(f"API endpoint: {registry.api_endpoint}")
        print(f"MLFlow URI: {registry.tracking_uri}")
        
        # Create another MLFlow run
        with mlflow.start_run() as run:
            mlflow.sklearn.log_model(create_test_model(), "model")
            run_id = run.info.run_id
        
        # Register via API
        result = registry.register_baseline_via_api(
            model_type="lead_scoring",
            mlflow_run_id=run_id,
            metadata={"test": "true"}
        )
        
        print("✓ API registration succeeded!")
        print(f"  Model ID: {result.model_id}")
        print(f"  Version: {result.version}")
        
    except Exception as e:
        print(f"✗ API registration failed: {type(e).__name__}")
        print(f"  Error: {str(e)}")

def print_solution_guide():
    """Print the solution guide for third parties."""
    print("\n\n" + "=" * 70)
    print("SOLUTION GUIDE FOR THIRD PARTIES")
    print("=" * 70)
    
    print("""
The 403 error occurs because the SDK defaults to a non-existent API endpoint.

IMMEDIATE FIXES:

1. For Local Development:
   ```python
   os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5001"
   registry = ModelRegistry()
   ```

2. For Production (when API is available):
   ```python
   os.environ["MLFLOW_TRACKING_URI"] = "https://mlflow.hokus.ai"  
   os.environ["MLFLOW_TRACKING_TOKEN"] = "your_mlflow_token"
   registry = ModelRegistry()
   ```

3. For Testing without MLFlow:
   ```python
   os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"
   registry = ModelRegistry()
   ```

COMPLETE WORKING EXAMPLE:
```python
import os
import mlflow
from hokusai import ModelRegistry

# Configure for your environment
os.environ["HOKUSAI_API_KEY"] = "your_api_key"
os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5001"  # or production URL

# Create MLFlow run first
mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
with mlflow.start_run() as run:
    # Log your model
    mlflow.sklearn.log_model(your_model, "model")
    run_id = run.info.run_id

# Register with Hokusai
registry = ModelRegistry()
result = registry.register_tokenized_model(
    model_uri=f"runs:/{run_id}/model",
    model_name="your-model-name",
    token_id="your-token-id",
    metric_name="accuracy",
    baseline_value=0.93
)
```
""")

if __name__ == "__main__":
    test_registration_scenario()
    print_solution_guide()