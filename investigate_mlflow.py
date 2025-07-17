#!/usr/bin/env python3
"""
Deep investigation into MLflow configuration and auth issues.
"""

import os
import requests
import json
from datetime import datetime

API_KEY = os.getenv("HOKUSAI_API_KEY", "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL")

def test_endpoint(url, headers=None, method="GET", data=None, description=""):
    """Test an endpoint and return detailed results."""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"URL: {url}")
    print(f"Method: {method}")
    if headers:
        print(f"Headers: {json.dumps(headers, indent=2)}")
    if data:
        print(f"Data: {json.dumps(data, indent=2)}")
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        
        print(f"\nStatus: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        # Try to parse JSON response
        try:
            body = response.json()
            print(f"Body: {json.dumps(body, indent=2)}")
        except:
            print(f"Body (text): {response.text[:500]}")
        
        return response
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return None

def investigate_mlflow():
    """Comprehensive MLflow investigation."""
    print("="*70)
    print("MLFLOW CONFIGURATION INVESTIGATION")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"API Key: {API_KEY[:10]}...{API_KEY[-4:]}")
    
    # Test 1: Check what MLflow endpoints actually exist
    print("\n\n" + "="*70)
    print("SECTION 1: MLFLOW ENDPOINT DISCOVERY")
    print("="*70)
    
    mlflow_endpoints = [
        ("https://registry.hokus.ai/mlflow", "Direct MLflow root"),
        ("https://registry.hokus.ai/mlflow/", "Direct MLflow root with slash"),
        ("https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search", "Standard MLflow API path"),
        ("https://registry.hokus.ai/mlflow/ajax-api/2.0/mlflow/experiments/search", "Ajax API path"),
        ("https://registry.hokus.ai/ajax-api/2.0/mlflow/experiments/search", "Ajax API without /mlflow prefix"),
        ("https://registry.hokus.ai/api/mlflow", "Proxy root"),
        ("https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search", "Proxy with standard path"),
        ("https://registry.hokus.ai/api/mlflow/ajax-api/2.0/mlflow/experiments/search", "Proxy with ajax path"),
    ]
    
    for url, desc in mlflow_endpoints:
        test_endpoint(url, description=desc)
    
    # Test 2: Test authentication patterns
    print("\n\n" + "="*70)
    print("SECTION 2: AUTHENTICATION PATTERNS")
    print("="*70)
    
    auth_patterns = [
        {
            "headers": {"Authorization": f"Bearer {API_KEY}"},
            "description": "Bearer token in Authorization header"
        },
        {
            "headers": {"Authorization": f"{API_KEY}"},
            "description": "Raw API key in Authorization header"
        },
        {
            "headers": {"X-API-Key": API_KEY},
            "description": "API key in X-API-Key header"
        },
        {
            "headers": {"X-Hokusai-API-Key": API_KEY},
            "description": "API key in X-Hokusai-API-Key header"
        },
        {
            "headers": {
                "Authorization": f"Bearer {API_KEY}",
                "X-API-Key": API_KEY
            },
            "description": "Both Authorization and X-API-Key headers"
        }
    ]
    
    test_url = "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search"
    for pattern in auth_patterns:
        test_endpoint(test_url, headers=pattern["headers"], description=pattern["description"])
    
    # Test 3: Test auth service directly with different patterns
    print("\n\n" + "="*70)
    print("SECTION 3: AUTH SERVICE VALIDATION PATTERNS")
    print("="*70)
    
    auth_url = "https://auth.hokus.ai/api/v1/keys/validate"
    
    # Pattern 1: As shown in the fixed middleware
    test_endpoint(
        auth_url,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST",
        data={
            "service_id": "ml-platform",
            "client_ip": "127.0.0.1"
        },
        description="Auth validation (as per middleware fix)"
    )
    
    # Pattern 2: Without client_ip
    test_endpoint(
        auth_url,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST",
        data={
            "service_id": "ml-platform"
        },
        description="Auth validation (without client_ip)"
    )
    
    # Pattern 3: Different service IDs
    for service_id in ["mlflow", "api", "model-registry", "hokusai"]:
        test_endpoint(
            auth_url,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            method="POST",
            data={
                "service_id": service_id
            },
            description=f"Auth validation with service_id={service_id}"
        )
    
    # Test 4: Check if proxy is actually running
    print("\n\n" + "="*70)
    print("SECTION 4: PROXY SERVICE STATUS")
    print("="*70)
    
    proxy_endpoints = [
        ("https://registry.hokus.ai/api/health", "API health check"),
        ("https://registry.hokus.ai/api/", "API root"),
        ("https://registry.hokus.ai/api/models", "Models endpoint"),
        ("https://registry.hokus.ai/api/mlflow/health", "MLflow proxy health"),
    ]
    
    for url, desc in proxy_endpoints:
        # Try with auth
        test_endpoint(
            url, 
            headers={"Authorization": f"Bearer {API_KEY}"},
            description=f"{desc} (with auth)"
        )
        # Try without auth
        test_endpoint(url, description=f"{desc} (no auth)")

if __name__ == "__main__":
    investigate_mlflow()