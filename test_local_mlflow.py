#!/usr/bin/env python3
"""Test the local MLFlow server that's actually running."""

import os
import requests
import mlflow
from mlflow.tracking import MlflowClient

def test_local_mlflow():
    """Test connection to local MLFlow server."""
    print("Testing Local MLFlow Server")
    print("=" * 60)
    
    # The actual running MLFlow server
    mlflow_url = "http://localhost:5001"
    
    print(f"MLFlow URL: {mlflow_url}")
    
    # Test basic connectivity
    print("\n1. Testing basic connectivity...")
    try:
        response = requests.get(f"{mlflow_url}/health")
        print(f"   Health endpoint: {response.status_code}")
    except Exception as e:
        print(f"   Health endpoint failed: {e}")
    
    # Test MLFlow API endpoints
    endpoints = [
        "/api/2.0/mlflow/experiments/search",
        "/api/2.0/mlflow/registered-models/search",
        "/api/2.0/mlflow/model-versions/search"
    ]
    
    print("\n2. Testing MLFlow API endpoints (no auth)...")
    for endpoint in endpoints:
        try:
            response = requests.get(f"{mlflow_url}{endpoint}")
            print(f"   {endpoint}: {response.status_code}")
            if response.status_code != 200:
                print(f"      Response: {response.text[:100]}...")
        except Exception as e:
            print(f"   {endpoint}: Failed - {e}")
    
    # Test with MLFlow client
    print("\n3. Testing MLFlow Python client...")
    os.environ["MLFLOW_TRACKING_URI"] = mlflow_url
    mlflow.set_tracking_uri(mlflow_url)
    
    try:
        client = MlflowClient()
        experiments = client.search_experiments(max_results=1)
        print(f"   ✓ Successfully connected! Found {len(experiments)} experiments")
        
        # Try to create a model version (this is where 403 happens)
        print("\n4. Testing model registration...")
        try:
            # First create a registered model
            model_name = "test-model-auth-check"
            client.create_registered_model(name=model_name)
            print(f"   ✓ Created registered model: {model_name}")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   Model already exists, continuing...")
            else:
                print(f"   ✗ Failed to create model: {e}")
        
        # Try to create a model version
        try:
            model_version = client.create_model_version(
                name=model_name,
                source="file:///tmp/model",
                description="Testing auth"
            )
            print(f"   ✓ Created model version: {model_version.version}")
        except Exception as e:
            print(f"   ✗ Failed to create model version: {e}")
            if "403" in str(e):
                print("   >>> This is the 403 error third parties are seeing!")
                
    except Exception as e:
        print(f"   ✗ MLFlow client failed: {e}")
    
    # Test the Hokusai API endpoint
    print("\n5. Testing Hokusai API MLFlow proxy...")
    hokusai_api_url = "http://localhost:8001"
    try:
        response = requests.get(f"{hokusai_api_url}/health")
        print(f"   Hokusai API health: {response.status_code}")
        
        # Test MLFlow proxy endpoint
        response = requests.get(f"{hokusai_api_url}/mlflow/api/2.0/mlflow/experiments/search")
        print(f"   MLFlow via proxy (no auth): {response.status_code}")
        
        # With a dummy API key
        headers = {"Authorization": "Bearer test_key_123"}
        response = requests.get(
            f"{hokusai_api_url}/mlflow/api/2.0/mlflow/experiments/search",
            headers=headers
        )
        print(f"   MLFlow via proxy (with auth): {response.status_code}")
        
    except Exception as e:
        print(f"   Hokusai API test failed: {e}")
    
    print("\n" + "=" * 60)
    print("DIAGNOSIS SUMMARY")
    print("=" * 60)
    print("\nThe issue is that:")
    print("1. MLFlow server is running locally on port 5001")
    print("2. It allows reading (GET) without auth")
    print("3. It requires auth for writing (POST) - this causes the 403")
    print("4. The SDK is trying to use 'https://api.hokus.ai' which doesn't exist")
    print("5. Third parties need to either:")
    print("   - Use the local MLFlow server with proper auth")
    print("   - Use a properly configured remote MLFlow server")

if __name__ == "__main__":
    test_local_mlflow()