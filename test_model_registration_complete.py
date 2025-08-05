#!/usr/bin/env python3
"""
Complete test of model registration with the new platform API key
"""

import os
import mlflow
from mlflow.tracking import MlflowClient
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.datasets import load_iris
import requests

# Configuration
API_KEY = os.environ.get("HOKUSAI_API_KEY", "hk_live_NVWOYDfNfTJyFzUDkQDBk2LLA4pB5qza")
MLFLOW_TRACKING_URI = "https://registry.hokus.ai/api/mlflow"

def test_auth():
    """Test if the API key works"""
    print("Testing API Key Authentication...")
    response = requests.get(
        f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/experiments/search",
        headers={"X-API-Key": API_KEY}
    )
    print(f"Auth test status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Authentication successful!")
        return True
    else:
        print(f"❌ Authentication failed: {response.text}")
        return False

def test_model_registration():
    """Test complete model registration flow"""
    
    print("\n" + "="*60)
    print("MLflow Model Registration Test")
    print("="*60)
    
    # Set up MLflow
    print(f"\nAPI Key: {API_KEY[:20]}...")
    print(f"MLflow URI: {MLFLOW_TRACKING_URI}")
    
    # Test authentication first
    if not test_auth():
        return False
    
    # Configure MLflow
    os.environ["MLFLOW_TRACKING_TOKEN"] = API_KEY
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    
    print("\nConfiguring MLflow client...")
    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
    
    try:
        # Create or get experiment
        experiment_name = "test-model-registration"
        print(f"\nCreating/getting experiment: {experiment_name}")
        
        try:
            experiment = client.get_experiment_by_name(experiment_name)
            if experiment:
                experiment_id = experiment.experiment_id
                print(f"✅ Using existing experiment: {experiment_id}")
            else:
                experiment_id = client.create_experiment(experiment_name)
                print(f"✅ Created new experiment: {experiment_id}")
        except Exception as e:
            experiment_id = client.create_experiment(experiment_name)
            print(f"✅ Created new experiment: {experiment_id}")
        
        # Train a simple model
        print("\nTraining sample model...")
        X, y = load_iris(return_X_y=True)
        model = LogisticRegression(max_iter=200)
        model.fit(X, y)
        accuracy = model.score(X, y)
        print(f"✅ Model trained with accuracy: {accuracy:.3f}")
        
        # Start MLflow run
        print("\nLogging to MLflow...")
        with mlflow.start_run(experiment_id=experiment_id) as run:
            # Log metrics
            mlflow.log_metric("accuracy", accuracy)
            mlflow.log_metric("samples", len(X))
            
            # Log parameters
            mlflow.log_param("model_type", "LogisticRegression")
            mlflow.log_param("max_iter", 200)
            
            # Log model
            mlflow.sklearn.log_model(
                model, 
                "model",
                registered_model_name="test-iris-classifier"
            )
            
            run_id = run.info.run_id
            print(f"✅ Run logged with ID: {run_id}")
        
        print("\n" + "="*60)
        print("✅ SUCCESS: Model Registration Complete!")
        print("="*60)
        print(f"- Experiment: {experiment_name} ({experiment_id})")
        print(f"- Run ID: {run_id}")
        print(f"- Model: test-iris-classifier")
        print(f"- Accuracy: {accuracy:.3f}")
        
        # List registered models
        print("\nRegistered Models:")
        try:
            models = client.search_registered_models()
            for rm in models:
                print(f"  - {rm.name} (version {rm.latest_versions[0].version if rm.latest_versions else 'N/A'})")
        except Exception as e:
            print(f"  Could not list models: {e}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during model registration: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_model_registration()
    if success:
        print("\n🎉 Model registration workflow is fully operational!")
    else:
        print("\n⚠️ Model registration failed - check the errors above")