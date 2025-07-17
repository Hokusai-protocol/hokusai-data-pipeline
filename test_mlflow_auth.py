#!/usr/bin/env python3
"""Test script to diagnose MLFlow 403 authentication error."""

import os
import sys
import mlflow
import requests
from mlflow.tracking import MlflowClient

def test_direct_mlflow_connection():
    """Test direct MLFlow connection without Hokusai SDK."""
    print("=" * 70)
    print("TESTING DIRECT MLFLOW CONNECTION")
    print("=" * 70)
    
    # Get tracking URI from environment or use default
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "https://registry.hokus.ai/mlflow")
    print(f"MLFlow Tracking URI: {tracking_uri}")
    
    # Check authentication environment variables
    print("\nAuthentication Configuration:")
    print(f"MLFLOW_TRACKING_TOKEN: {'SET' if os.getenv('MLFLOW_TRACKING_TOKEN') else 'NOT SET'}")
    print(f"MLFLOW_TRACKING_USERNAME: {'SET' if os.getenv('MLFLOW_TRACKING_USERNAME') else 'NOT SET'}")
    print(f"MLFLOW_TRACKING_PASSWORD: {'SET' if os.getenv('MLFLOW_TRACKING_PASSWORD') else 'NOT SET'}")
    print(f"HOKUSAI_API_KEY: {'SET' if os.getenv('HOKUSAI_API_KEY') else 'NOT SET'}")
    
    # Set tracking URI
    mlflow.set_tracking_uri(tracking_uri)
    
    try:
        # Test 1: Direct API call to check server accessibility
        print("\nTest 1: Checking MLFlow server accessibility...")
        response = requests.get(f"{tracking_uri}/api/2.0/mlflow/experiments/search")
        print(f"Response status: {response.status_code}")
        if response.status_code == 403:
            print("ERROR: 403 Forbidden - MLFlow server requires authentication")
            print(f"Response headers: {dict(response.headers)}")
            print(f"Response body: {response.text[:500]}")
        
        # Test 2: Using MLFlow client
        print("\nTest 2: Testing MLFlow client...")
        client = MlflowClient()
        experiments = client.search_experiments(max_results=1)
        print(f"Success! Found {len(experiments)} experiments")
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {str(e)}")
        if "403" in str(e):
            print("\nMLFlow server returned 403 Forbidden. This means:")
            print("1. The MLFlow server requires authentication")
            print("2. No valid authentication credentials were provided")
            print("3. Or the provided credentials are invalid/insufficient")


def test_hokusai_sdk_connection():
    """Test connection through Hokusai SDK."""
    print("\n" + "=" * 70)
    print("TESTING HOKUSAI SDK CONNECTION")
    print("=" * 70)
    
    api_key = os.getenv("HOKUSAI_API_KEY")
    if not api_key:
        print("ERROR: HOKUSAI_API_KEY not set in environment")
        return
    
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    
    try:
        # Import and configure Hokusai
        from hokusai import setup, ModelRegistry
        from hokusai.config import setup_mlflow_auth
        
        # Setup Hokusai
        print("\nSetting up Hokusai SDK...")
        setup(api_key=api_key)
        
        # Try to setup MLFlow auth
        print("Setting up MLFlow authentication...")
        setup_mlflow_auth(validate=False)
        
        # Create registry
        print("Creating ModelRegistry...")
        registry = ModelRegistry()
        
        # Test listing models
        print("Testing model listing...")
        models = registry.list_models_by_type("test")
        print(f"Success! Registry is accessible")
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()


def test_mlflow_auth_methods():
    """Test different MLFlow authentication methods."""
    print("\n" + "=" * 70)
    print("TESTING MLFLOW AUTHENTICATION METHODS")
    print("=" * 70)
    
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "https://registry.hokus.ai/mlflow")
    
    # Test 1: No auth
    print("\nTest 1: No authentication...")
    os.environ.pop("MLFLOW_TRACKING_TOKEN", None)
    os.environ.pop("MLFLOW_TRACKING_USERNAME", None)
    os.environ.pop("MLFLOW_TRACKING_PASSWORD", None)
    mlflow.set_tracking_uri(tracking_uri)
    
    try:
        client = MlflowClient()
        client.search_experiments(max_results=1)
        print("Success: MLFlow server accepts unauthenticated requests")
    except Exception as e:
        print(f"Failed: {str(e)}")
    
    # Test 2: Bearer token from HOKUSAI_API_KEY
    print("\nTest 2: Using HOKUSAI_API_KEY as bearer token...")
    api_key = os.getenv("HOKUSAI_API_KEY")
    if api_key:
        os.environ["MLFLOW_TRACKING_TOKEN"] = api_key
        mlflow.set_tracking_uri(tracking_uri)
        
        try:
            client = MlflowClient()
            client.search_experiments(max_results=1)
            print("Success: MLFlow server accepts HOKUSAI_API_KEY as token")
        except Exception as e:
            print(f"Failed: {str(e)}")
    
    # Test 3: Check if MLFlow is behind Hokusai API proxy
    print("\nTest 3: Checking if MLFlow is proxied through Hokusai API...")
    if api_key:
        headers = {"Authorization": f"Bearer {api_key}"}
        
        # Try Hokusai API endpoint
        try:
            response = requests.get(
                "https://api.hokus.ai/mlflow/api/2.0/mlflow/experiments/search",
                headers=headers
            )
            print(f"Hokusai API proxy status: {response.status_code}")
            if response.status_code == 200:
                print("Success: MLFlow is accessible through Hokusai API proxy")
        except Exception as e:
            print(f"Failed to access through proxy: {e}")


def check_mlflow_server_info():
    """Get information about the MLFlow server configuration."""
    print("\n" + "=" * 70)
    print("MLFLOW SERVER INFORMATION")
    print("=" * 70)
    
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "https://registry.hokus.ai/mlflow")
    
    # Check different endpoints
    endpoints = [
        "/",
        "/health",
        "/version",
        "/api/2.0/mlflow/experiments/search",
        "/api/2.0/mlflow/registered-models/search"
    ]
    
    for endpoint in endpoints:
        url = f"{tracking_uri}{endpoint}"
        try:
            response = requests.get(url, timeout=5)
            print(f"\n{endpoint}:")
            print(f"  Status: {response.status_code}")
            if response.status_code == 401:
                print("  Auth: Required (401 Unauthorized)")
            elif response.status_code == 403:
                print("  Auth: Required (403 Forbidden)")
            elif response.status_code == 200:
                print("  Auth: Not required or valid")
            
            # Check for auth headers in response
            if "WWW-Authenticate" in response.headers:
                print(f"  Auth-Scheme: {response.headers['WWW-Authenticate']}")
                
        except Exception as e:
            print(f"  Error: {str(e)}")


if __name__ == "__main__":
    print("MLFlow Authentication Diagnostic Script")
    print("======================================")
    print(f"Python: {sys.version}")
    print(f"MLFlow: {mlflow.__version__}")
    
    # Run all tests
    test_direct_mlflow_connection()
    test_hokusai_sdk_connection()
    test_mlflow_auth_methods()
    check_mlflow_server_info()
    
    print("\n" + "=" * 70)
    print("DIAGNOSIS COMPLETE")
    print("=" * 70)