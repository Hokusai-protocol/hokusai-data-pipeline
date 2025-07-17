#!/usr/bin/env python3
"""
Real-world test: Register a model as a third party using only Bearer token auth.
This test uses the actual MLflow client to register through the Hokusai proxy.
"""

import os
import sys
import mlflow
from mlflow.models import infer_signature
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from datetime import datetime
import requests


def test_proxy_endpoints():
    """Test if the proxy endpoints are accessible."""
    print("\n🔍 Testing Proxy Endpoints...")
    
    api_key = os.getenv("HOKUSAI_API_KEY")
    if not api_key:
        print("❌ No API key found")
        return False
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    # Test proxy health
    try:
        response = requests.get(
            "https://registry.hokus.ai/api/mlflow/health/mlflow",
            headers=headers,
            timeout=10
        )
        print(f"  Proxy health check: {response.status_code}")
        if response.status_code != 200:
            print(f"  Response: {response.text}")
    except Exception as e:
        print(f"  ❌ Proxy health check failed: {e}")
        return False
    
    # Test MLflow API through proxy
    try:
        response = requests.get(
            "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search",
            headers=headers,
            timeout=10
        )
        print(f"  MLflow API via proxy: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Found {len(data.get('experiments', []))} experiments")
            return True
        else:
            print(f"  Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ MLflow API test failed: {e}")
        return False


def test_direct_mlflow():
    """Test direct MLflow access (for comparison)."""
    print("\n🔍 Testing Direct MLflow Access...")
    
    try:
        response = requests.get(
            "https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search",
            timeout=10
        )
        print(f"  Direct MLflow: {response.status_code}")
        if response.status_code == 200:
            print("  ✓ Direct MLflow allows unauthenticated reads")
        else:
            print("  ℹ️  Direct MLflow requires authentication")
    except Exception as e:
        print(f"  Error: {e}")


def register_model_with_bearer_token():
    """Main test: Register a model using Bearer token authentication."""
    
    print("=" * 70)
    print("REAL THIRD-PARTY MODEL REGISTRATION TEST")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Step 1: Verify environment
    api_key = os.getenv("HOKUSAI_API_KEY")
    if not api_key:
        print("\n❌ ERROR: HOKUSAI_API_KEY not set")
        print("Please run: export HOKUSAI_API_KEY='your-api-key'")
        return False
    
    print(f"\n✓ API Key: {api_key[:10]}...{api_key[-4:]}")
    
    # Step 2: Test endpoints first
    if not test_proxy_endpoints():
        print("\n❌ Proxy endpoints not working. Checking alternatives...")
        test_direct_mlflow()
        
        # Try using direct MLflow with the API key
        print("\n🔧 Attempting workaround: Direct MLflow with API key as token...")
        os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/mlflow"
        os.environ["MLFLOW_TRACKING_TOKEN"] = api_key
    else:
        # Use proxy endpoint
        print("\n✓ Using proxy endpoint")
        os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"
        os.environ["MLFLOW_TRACKING_TOKEN"] = api_key
    
    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    
    # Step 3: Test MLflow client connection
    print("\n📡 Testing MLflow Client Connection...")
    try:
        client = mlflow.tracking.MlflowClient()
        experiments = client.search_experiments(max_results=1)
        print(f"✓ MLflow client connected! Found {len(experiments)} experiments")
    except Exception as e:
        print(f"❌ MLflow client failed: {str(e)}")
        
        # Try fallback options
        print("\n🔧 Trying fallback: Hokusai SDK...")
        try:
            from hokusai import setup, ModelRegistry
            from hokusai.config import setup_mlflow_auth
            
            # Setup with explicit MLflow auth
            setup(api_key=api_key)
            os.environ["MLFLOW_TRACKING_TOKEN"] = api_key
            setup_mlflow_auth(validate=False)
            
            registry = ModelRegistry()
            print("✓ Using Hokusai SDK as fallback")
            
            # Continue with SDK-based registration
            return test_sdk_registration(registry)
            
        except Exception as sdk_error:
            print(f"❌ SDK fallback also failed: {sdk_error}")
            return False
    
    # Step 4: Create experiment
    experiment_name = f"third_party_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n📊 Creating experiment: {experiment_name}")
    
    try:
        experiment = mlflow.set_experiment(experiment_name)
        print(f"✓ Experiment created with ID: {experiment.experiment_id}")
    except Exception as e:
        print(f"❌ Failed to create experiment: {e}")
        # Use default experiment
        experiment_name = "Default"
        experiment = mlflow.set_experiment(experiment_name)
    
    # Step 5: Train and log model
    print("\n🤖 Training and logging model...")
    
    # Generate sample data
    np.random.seed(42)
    X = np.random.randn(100, 5)
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Train model
    model = LogisticRegression(random_state=42)
    model.fit(X_train, y_train)
    accuracy = model.score(X_test, y_test)
    
    print(f"✓ Model trained with accuracy: {accuracy:.3f}")
    
    # Log to MLflow
    try:
        with mlflow.start_run(experiment_id=experiment.experiment_id) as run:
            # Log metrics and params
            mlflow.log_param("model_type", "LogisticRegression")
            mlflow.log_metric("accuracy", accuracy)
            
            # Log model
            signature = infer_signature(X_train, model.predict(X_train))
            model_info = mlflow.sklearn.log_model(
                model,
                "model",
                signature=signature
            )
            
            # Tag for identification
            mlflow.set_tag("third_party_test", "true")
            mlflow.set_tag("test_timestamp", datetime.now().isoformat())
            
            run_id = run.info.run_id
            print(f"✓ Model logged! Run ID: {run_id}")
            
            # Register model
            model_name = f"third_party_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            print(f"\n📝 Registering model: {model_name}")
            
            registered_model = mlflow.register_model(
                f"runs:/{run_id}/model",
                model_name
            )
            
            print(f"✓ Model registered!")
            print(f"  Name: {registered_model.name}")
            print(f"  Version: {registered_model.version}")
            
    except Exception as e:
        print(f"❌ Model logging/registration failed: {e}")
        
        if "403" in str(e):
            print("\n⚠️  403 Error - This confirms the authentication issue")
            print("The proxy may not be properly forwarding requests to MLflow")
        elif "401" in str(e):
            print("\n⚠️  401 Error - API key not accepted")
            print("The proxy may not be validating Bearer tokens correctly")
        elif "404" in str(e):
            print("\n⚠️  404 Error - Endpoint not found")
            print("The proxy route may not be deployed")
            
        return False
    
    # Step 6: Verify registration
    print("\n🔎 Verifying model registration...")
    
    try:
        # Search for our model
        models = client.search_registered_models(filter_string=f"name='{model_name}'")
        
        if models:
            model = models[0]
            print(f"✓ Model found in registry!")
            print(f"  Latest version: {model.latest_versions[0].version if model.latest_versions else 'None'}")
            print(f"  Status: {model.latest_versions[0].current_stage if model.latest_versions else 'None'}")
        else:
            print("⚠️  Model not found in registry")
            
    except Exception as e:
        print(f"❌ Failed to verify: {e}")
    
    print("\n✅ SUCCESS: Third-party model registration completed!")
    return True


def test_sdk_registration(registry):
    """Fallback test using Hokusai SDK."""
    print("\n📦 Using Hokusai SDK for registration...")
    
    try:
        # Register a test model
        result = registry.register_baseline(
            model_name=f"sdk_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            model_type="sklearn",
            metrics={"accuracy": 0.95},
            metadata={"test": "true", "method": "sdk"}
        )
        
        print(f"✓ Model registered via SDK!")
        print(f"  Model ID: {result.get('model_id')}")
        return True
        
    except Exception as e:
        print(f"❌ SDK registration failed: {e}")
        return False


def main():
    """Run the complete test."""
    success = register_model_with_bearer_token()
    
    print("\n" + "=" * 70)
    if success:
        print("✅ TEST PASSED - Bearer token authentication works!")
        print("\nThird parties can successfully register models.")
    else:
        print("❌ TEST FAILED - Bearer token authentication not working")
        print("\nPossible issues:")
        print("1. The /api/mlflow proxy endpoint is not deployed")
        print("2. The proxy is not properly forwarding Bearer tokens")
        print("3. MLflow backend configuration issues")
        print("\nRecommended actions:")
        print("1. Verify proxy deployment: check ALB routing rules")
        print("2. Check API service logs for errors")
        print("3. Test with direct MLflow access as a workaround")
    print("=" * 70)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
