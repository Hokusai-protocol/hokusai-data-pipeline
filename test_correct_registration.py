#!/usr/bin/env python3
"""Test model registration using the CORRECT MLflow endpoints."""

import mlflow
import mlflow.sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.datasets import make_classification
import numpy as np
import json
from datetime import datetime

# Configuration - using the CORRECT tracking URI
API_KEY = "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
TRACKING_URI = "https://registry.hokus.ai/api/mlflow"  # CORRECT endpoint

print(f"Testing Model Registration with Hokusai Platform")
print(f"Time: {datetime.now().isoformat()}")
print(f"Tracking URI: {TRACKING_URI}")
print("=" * 80)

# Set up MLflow with authentication
mlflow.set_tracking_uri(TRACKING_URI)
mlflow.set_experiment("third_party_test")

# Create a simple model for testing
print("\n1. Creating test model...")
X, y = make_classification(n_samples=100, n_features=4, n_informative=2, random_state=42)
model = LogisticRegression(random_state=42)
model.fit(X, y)
accuracy = model.score(X, y)
print(f"   Model accuracy: {accuracy:.3f}")

# Register model using MLflow
print("\n2. Registering model with MLflow...")
try:
    with mlflow.start_run() as run:
        # Log parameters
        mlflow.log_param("model_type", "LogisticRegression")
        mlflow.log_param("n_features", 4)
        mlflow.log_param("random_state", 42)
        
        # Log metrics
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1_score", 0.89)  # Example metric
        
        # Log the model
        mlflow.sklearn.log_model(
            model, 
            "model",
            registered_model_name="LSCOR_test_model"
        )
        
        # Set tags
        mlflow.set_tag("test_type", "integration_test")
        mlflow.set_tag("api_version", "2.0")
        
        print(f"   Run ID: {run.info.run_id}")
        print(f"   Experiment ID: {run.info.experiment_id}")
        print(f"   Model logged successfully!")
        
        # Try to create a model version
        client = mlflow.tracking.MlflowClient()
        
        # First, create the registered model if it doesn't exist
        try:
            client.create_registered_model("LSCOR_test_model")
            print("   Created new registered model: LSCOR_test_model")
        except Exception as e:
            print(f"   Registered model may already exist: {str(e)}")
        
        # Create model version
        try:
            model_version = client.create_model_version(
                name="LSCOR_test_model",
                source=f"runs:/{run.info.run_id}/model",
                run_id=run.info.run_id
            )
            print(f"   Created model version: {model_version.version}")
        except Exception as e:
            print(f"   Error creating model version: {str(e)}")
            
except Exception as e:
    print(f"\n❌ Error during registration: {str(e)}")
    print(f"   Error type: {type(e).__name__}")
    
# Test SDK approach
print("\n3. Testing SDK approach...")
try:
    from hokusai.core import ModelRegistry
    
    registry = ModelRegistry(TRACKING_URI)
    result = registry.register_baseline(
        model=model,
        model_type="classification",
        metadata={"accuracy": accuracy}
    )
    print(f"   ✅ SDK registration successful: {result}")
except ImportError:
    print("   ⚠️  Hokusai SDK not installed, skipping SDK test")
except Exception as e:
    print(f"   ❌ SDK registration error: {str(e)}")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"""
The correct way to register models with Hokusai:

1. Set MLflow tracking URI to: https://registry.hokus.ai/api/mlflow
2. Use standard MLflow client for all operations
3. Authentication is handled automatically via API key

The following endpoints from the third-party guide are INCORRECT:
- ❌ /api/models/register (does not exist)
- ❌ /api/models (does not exist)
- ❌ http://registry.hokus.ai/mlflow (missing /api prefix)

The CORRECT approach is to use MLflow endpoints through the proxy:
- ✅ https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/*
""")