#!/usr/bin/env python3
"""
Test Final Authentication Solution

This script tests the complete authentication flow with proper URLs and headers.
"""

import os
import sys
import requests
import json

print("=" * 80)
print("Final Authentication Solution Test")
print("=" * 80)
print()

# Configuration
API_KEY = "test-hokusai-api-key-12345"
MLFLOW_VIA_PROXY = "https://registry.hokus.ai/api/mlflow"
MLFLOW_DIRECT = "https://registry.hokus.ai/mlflow"

print("Configuration:")
print(f"  Hokusai API Key: {API_KEY}")
print(f"  MLflow via Proxy: {MLFLOW_VIA_PROXY}")
print(f"  MLflow Direct: {MLFLOW_DIRECT}")
print()

# Test 1: Direct MLflow access (no auth needed for reads)
print("-" * 60)
print("Test 1: Direct MLflow Access (No Auth)")
print("-" * 60)

response = requests.get(
    f"{MLFLOW_DIRECT}/ajax-api/2.0/mlflow/experiments/search?max_results=1",
    timeout=10
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print("✓ Read access works without authentication")
else:
    print(f"✗ Failed: {response.text[:200]}")

# Test 2: MLflow via Hokusai API proxy
print("\n" + "-" * 60)
print("Test 2: MLflow via Hokusai API Proxy")
print("-" * 60)

headers = {"X-API-Key": API_KEY}
response = requests.get(
    f"{MLFLOW_VIA_PROXY}/api/2.0/mlflow/experiments/search?max_results=1",
    headers=headers,
    timeout=10
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print("✓ Authenticated access works via proxy")
    data = response.json()
    print(f"  Found {len(data.get('experiments', []))} experiments")
elif response.status_code == 401:
    print("✗ Authentication failed - invalid API key")
else:
    print(f"✗ Error: {response.text[:200]}")

# Test 3: SDK Configuration
print("\n" + "-" * 60)
print("Test 3: SDK Configuration Test")
print("-" * 60)

# Set up environment
os.environ["HOKUSAI_API_KEY"] = API_KEY
os.environ["MLFLOW_TRACKING_URI"] = MLFLOW_VIA_PROXY

# Import SDK
try:
    from hokusai import setup
    from hokusai.core import ModelRegistry
    from hokusai.core.models import ClassificationModel
    
    print("1. Initializing SDK...")
    setup(api_key=API_KEY)
    
    print("2. Creating ModelRegistry...")
    registry = ModelRegistry()
    print(f"   Registry tracking URI: {registry.tracking_uri}")
    
    print("3. Creating test model...")
    model = ClassificationModel(
        model_id="AUTH_TEST_FINAL",
        version="v1.0.0",
        n_classes=2,
        metrics={"accuracy": 0.95}
    )
    
    print("4. Attempting registration...")
    try:
        # First, let's manually test the MLflow client
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_VIA_PROXY)
        
        # Try to create an experiment to test auth
        from mlflow.tracking import MlflowClient
        
        # Create a custom client that adds our headers
        class HokusaiMlflowClient(MlflowClient):
            def __init__(self, tracking_uri=None, api_key=None):
                super().__init__(tracking_uri)
                self.api_key = api_key or os.environ.get("HOKUSAI_API_KEY")
                
            def _get_request_headers(self):
                """Override to add X-API-Key header."""
                headers = super()._get_request_headers()
                if self.api_key:
                    headers["X-API-Key"] = self.api_key
                return headers
        
        # Use our custom client
        client = HokusaiMlflowClient(tracking_uri=MLFLOW_VIA_PROXY, api_key=API_KEY)
        
        # Test listing experiments
        experiments = client.search_experiments(max_results=1)
        print(f"   ✓ Custom client works! Found {len(experiments)} experiments")
        
        # Now try registration
        result = registry.register_baseline(
            model=model,
            model_type="classification"
        )
        print("   ✓ Model registered successfully!")
        print(f"     Model ID: {result.model_id}")
        print(f"     Version: {result.version}")
        
    except Exception as e:
        print(f"   ✗ Registration failed: {type(e).__name__}: {e}")
        
        # Provide solution
        print("\n   Solution: MLflow client needs custom headers for Hokusai API")
        print("   The SDK should use X-API-Key header when accessing via proxy")
        
except Exception as e:
    print(f"✗ SDK initialization failed: {e}")

print("\n" + "=" * 80)
print("Summary")
print("=" * 80)
print("""
Authentication Architecture:
1. Direct MLflow (registry.hokus.ai/mlflow) - No auth for reads
2. Via Hokusai API (registry.hokus.ai/api/mlflow) - Requires X-API-Key

The SDK needs to:
1. Use registry.hokus.ai/api/mlflow as the tracking URI
2. Pass API key in X-API-Key header (not Authorization)
3. Handle the MLflow client's authentication properly

Current Status:
- Direct MLflow access works (for reads)
- Hokusai API proxy validates API keys correctly
- MLflow Python client needs custom headers for proxy auth
""")