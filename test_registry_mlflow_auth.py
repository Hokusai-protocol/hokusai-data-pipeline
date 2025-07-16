#!/usr/bin/env python3
"""
Test MLflow Authentication at registry.hokus.ai

This script tests the actual production MLflow endpoints and authentication.
"""

import os
import requests
import json

print("=" * 80)
print("MLflow Production Authentication Test")
print("=" * 80)
print()

# Configuration
BASE_URL = "https://registry.hokus.ai/mlflow"
API_KEY = os.environ.get("HOKUSAI_API_KEY", "test-api-key-12345")

print(f"MLflow Base URL: {BASE_URL}")
print(f"API Key: {'SET' if API_KEY else 'NOT SET'}")
print()

# Test endpoints
endpoints = [
    ("Experiments Search", "/ajax-api/2.0/mlflow/experiments/search?max_results=1"),
    ("Registered Models Search", "/ajax-api/2.0/mlflow/registered-models/search?max_results=1"),
    ("Model Versions Search", "/ajax-api/2.0/mlflow/model-versions/search?max_results=1"),
]

def test_endpoint(name, path, headers=None):
    """Test a specific MLflow endpoint."""
    url = BASE_URL + path
    print(f"\nTesting: {name}")
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, headers=headers or {}, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Success! Response keys: {list(data.keys())}")
        elif response.status_code == 401:
            print("Authentication required")
        elif response.status_code == 403:
            print("Forbidden - authentication failed")
        else:
            print(f"Response: {response.text[:200]}")
            
        return response
        
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        return None

# Test 1: Without authentication
print("\n" + "-" * 60)
print("Test 1: Without Authentication")
print("-" * 60)

for name, path in endpoints:
    test_endpoint(name, path)

# Test 2: With Bearer token
print("\n" + "-" * 60)
print("Test 2: With Bearer Token (Authorization: Bearer)")
print("-" * 60)

bearer_headers = {"Authorization": f"Bearer {API_KEY}"}
for name, path in endpoints:
    test_endpoint(name, path, bearer_headers)

# Test 3: With X-API-Key header
print("\n" + "-" * 60)
print("Test 3: With X-API-Key Header")
print("-" * 60)

api_key_headers = {"X-API-Key": API_KEY}
for name, path in endpoints:
    test_endpoint(name, path, api_key_headers)

# Test 4: MLflow specific authentication
print("\n" + "-" * 60)
print("Test 4: MLflow Environment Variable Setup")
print("-" * 60)

# Show how to configure MLflow client
print("\nFor MLflow Python client, set:")
print(f'os.environ["MLFLOW_TRACKING_URI"] = "{BASE_URL}"')
print(f'os.environ["MLFLOW_TRACKING_TOKEN"] = "{API_KEY}"')
print("\nOr for basic auth:")
print(f'os.environ["MLFLOW_TRACKING_USERNAME"] = "token"')
print(f'os.environ["MLFLOW_TRACKING_PASSWORD"] = "{API_KEY}"')

# Test with MLflow client
print("\n" + "-" * 60)
print("Test 5: Using MLflow Python Client")
print("-" * 60)

try:
    import mlflow
    
    # Set up MLflow
    os.environ["MLFLOW_TRACKING_URI"] = BASE_URL
    os.environ["MLFLOW_TRACKING_TOKEN"] = API_KEY
    
    mlflow.set_tracking_uri(BASE_URL)
    
    # Try to list experiments
    print("Attempting to list experiments...")
    experiments = mlflow.search_experiments(max_results=1)
    print(f"Success! Found {len(experiments)} experiments")
    
except Exception as e:
    print(f"MLflow client error: {type(e).__name__}: {e}")

print("\n" + "=" * 80)
print("Test Complete")
print("=" * 80)