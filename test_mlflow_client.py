#\!/usr/bin/env python3
import os
import mlflow
from mlflow.tracking import MlflowClient

# Set up environment
os.environ["HOKUSAI_API_KEY"] = "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"

print("Testing MLflow client configurations...")
print(f"API Key: {os.environ['HOKUSAI_API_KEY'][:10]}...{os.environ['HOKUSAI_API_KEY'][-4:]}\n")

# Test 1: Direct MLflow with ajax-api path
print("Test 1: Direct MLflow with ajax-api path")
try:
    mlflow.set_tracking_uri("https://registry.hokus.ai/mlflow")
    client = MlflowClient()
    experiments = client.search_experiments()
    print(f"✅ SUCCESS\! Found {len(experiments)} experiments")
    for exp in experiments[:3]:
        print(f"  - {exp.name} (ID: {exp.experiment_id})")
except Exception as e:
    print(f"❌ Failed: {e}\n")

# Test 2: Via proxy endpoint
print("\nTest 2: Via API proxy endpoint")
try:
    mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")
    client = MlflowClient()
    experiments = client.search_experiments()
    print(f"✅ SUCCESS\! Found {len(experiments)} experiments")
except Exception as e:
    print(f"❌ Failed: {e}\n")

# Test 3: Try to create and register a simple model
print("\nTest 3: Model registration attempt")
try:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    
    # Create a simple model
    X = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
    y = np.array([0, 0, 1, 1])
    model = LogisticRegression()
    model.fit(X, y)
    
    # Try to log the model
    with mlflow.start_run() as run:
        mlflow.sklearn.log_model(model, "model")
        print(f"✅ Model logged\! Run ID: {run.info.run_id}")
        
        # Try to register the model
        model_uri = f"runs:/{run.info.run_id}/model"
        model_name = "test-hokusai-registration"
        mlflow.register_model(model_uri, model_name)
        print(f"✅ Model registered as '{model_name}'\!")
        
except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback
    traceback.print_exc()
