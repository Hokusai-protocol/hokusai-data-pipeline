#!/usr/bin/env python3
"""
Simple test for model registration after artifact storage fixes
"""
import os
import sys
import mlflow
from mlflow.models import infer_signature
import numpy as np
from sklearn.linear_model import LogisticRegression
from datetime import datetime

def main():
    # Get API key from environment
    api_key = os.getenv("HOKUSAI_API_KEY")
    if not api_key:
        print("❌ Error: HOKUSAI_API_KEY environment variable not set")
        return False
    
    print("=" * 70)
    print("SIMPLE MODEL REGISTRATION TEST")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print()
    
    # Configure MLflow
    tracking_uri = "https://registry.hokus.ai/api/mlflow"
    print(f"🔧 Configuring MLflow...")
    print(f"   Tracking URI: {tracking_uri}")
    
    os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
    os.environ["MLFLOW_TRACKING_TOKEN"] = api_key
    mlflow.set_tracking_uri(tracking_uri)
    
    try:
        # Test connection
        print("\n📡 Testing MLflow connection...")
        client = mlflow.tracking.MlflowClient()
        experiments = client.search_experiments()
        print(f"✅ Connected! Found {len(experiments)} experiments")
        
        # Create a simple model
        print("\n🤖 Creating test model...")
        X_train = np.random.rand(100, 5)
        y_train = np.random.randint(0, 2, 100)
        
        model = LogisticRegression(max_iter=100)
        model.fit(X_train, y_train)
        accuracy = model.score(X_train, y_train)
        print(f"✅ Model trained with accuracy: {accuracy:.3f}")
        
        # Log model to MLflow
        print("\n📦 Logging model to MLflow...")
        with mlflow.start_run() as run:
            # Log metrics
            mlflow.log_metric("accuracy", accuracy)
            mlflow.log_metric("test_metric", 0.95)
            
            # Log model
            signature = infer_signature(X_train, y_train)
            mlflow.sklearn.log_model(
                model, 
                "model",
                signature=signature,
                registered_model_name="test-model-registration"
            )
            
            run_id = run.info.run_id
            print(f"✅ Model logged! Run ID: {run_id}")
        
        # Verify model was registered
        print("\n🔍 Verifying model registration...")
        registered_models = client.search_registered_models()
        test_model = None
        for rm in registered_models:
            if rm.name == "test-model-registration":
                test_model = rm
                break
        
        if test_model:
            print(f"✅ Model registered successfully!")
            print(f"   Name: {test_model.name}")
            print(f"   Latest version: {test_model.latest_versions[0].version if test_model.latest_versions else 'None'}")
            
            # Try to load the model
            print("\n📥 Testing model download...")
            model_uri = f"models:/{test_model.name}/latest"
            loaded_model = mlflow.sklearn.load_model(model_uri)
            print("✅ Model downloaded successfully!")
            
            # Test prediction
            test_data = np.random.rand(5, 5)
            predictions = loaded_model.predict(test_data)
            print(f"✅ Model predictions work! Sample: {predictions[:5]}")
            
            print("\n" + "=" * 70)
            print("✅ ALL TESTS PASSED! Model registration is working!")
            print("=" * 70)
            return True
        else:
            print("❌ Model was not found in registry")
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)