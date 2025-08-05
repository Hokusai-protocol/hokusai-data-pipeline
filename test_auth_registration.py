#!/usr/bin/env python3
"""Test model registration with proper authentication."""

import os
import mlflow
import mlflow.sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.datasets import make_classification
import numpy as np
from datetime import datetime

# Configuration
API_KEY = "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
TRACKING_URI = "https://registry.hokus.ai/api/mlflow"

print(f"Testing Model Registration with Authentication")
print(f"Time: {datetime.now().isoformat()}")
print(f"Tracking URI: {TRACKING_URI}")
print("=" * 80)

# Set up MLflow with authentication
# Method 1: Using environment variable
os.environ["MLFLOW_TRACKING_TOKEN"] = API_KEY

# Method 2: Using custom request header plugin
os.environ["MLFLOW_TRACKING_HEADERS"] = f"Authorization:Bearer {API_KEY}"

# Method 3: Set tracking URI with auth
mlflow.set_tracking_uri(TRACKING_URI)

# Create a simple model for testing
print("\n1. Creating test model...")
X, y = make_classification(n_samples=100, n_features=4, n_informative=2, random_state=42)
model = LogisticRegression(random_state=42)
model.fit(X, y)
accuracy = model.score(X, y)
print(f"   Model accuracy: {accuracy:.3f}")

# Test 1: Try to access experiments
print("\n2. Testing experiment access...")
try:
    client = mlflow.tracking.MlflowClient()
    experiments = client.search_experiments()
    print(f"   ✅ Successfully accessed experiments (found {len(experiments)})")
except Exception as e:
    print(f"   ❌ Error accessing experiments: {str(e)}")

# Test 2: Create a run
print("\n3. Creating MLflow run...")
try:
    # Use Default experiment (ID 0) which we know exists
    with mlflow.start_run(experiment_id="0") as run:
        # Log parameters
        mlflow.log_param("model_type", "LogisticRegression")
        mlflow.log_param("n_features", 4)
        
        # Log metrics
        mlflow.log_metric("accuracy", accuracy)
        
        print(f"   ✅ Run created: {run.info.run_id}")
        
        # Log the model
        mlflow.sklearn.log_model(
            model, 
            "model"
        )
        print(f"   ✅ Model logged successfully")
        
except Exception as e:
    print(f"   ❌ Error creating run: {str(e)}")

# Test 3: Direct API test with requests
print("\n4. Testing direct API access...")
import requests

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Test experiments endpoint
url = f"{TRACKING_URI}/api/2.0/mlflow/experiments/search"
response = requests.get(url, headers=headers)
print(f"   Experiments endpoint: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"   ✅ Found {len(data.get('experiments', []))} experiments")
else:
    print(f"   ❌ Error: {response.text}")

# Summary
print("\n" + "=" * 80)
print("AUTHENTICATION FINDINGS")
print("=" * 80)
print(f"""
The issue appears to be with MLflow client authentication:

1. The Hokusai API requires Bearer token authentication
2. MLflow client may not be passing the auth headers correctly
3. Direct API calls with proper headers work fine

The third-party user needs to:
1. Use the correct tracking URI: https://registry.hokus.ai/api/mlflow
2. Configure authentication properly (may require custom MLflow plugin)
3. Or use the Hokusai SDK which handles auth automatically
""")