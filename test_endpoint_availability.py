#!/usr/bin/env python3
"""Test Hokusai API endpoints availability."""

import requests
import json
from datetime import datetime

# Configuration
API_KEY = "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
BASE_URL = "https://registry.hokus.ai"

# Headers
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def test_endpoint(method, endpoint, description, data=None):
    """Test a single endpoint and return result."""
    url = f"{BASE_URL}{endpoint}"
    print(f"\nTesting: {description}")
    print(f"  {method} {url}")
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        else:
            response = requests.request(method, url, headers=headers, json=data)
        
        print(f"  Status: {response.status_code}")
        
        # Check content type
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type and response.status_code == 404:
            print(f"  Response: HTML 404 page (endpoint not found)")
        elif 'application/json' in content_type:
            try:
                body = response.json()
                print(f"  Response: {json.dumps(body, indent=2)[:200]}...")
            except:
                print(f"  Response: {response.text[:200]}...")
        else:
            print(f"  Response: {response.text[:200]}...")
            
        return {
            "endpoint": endpoint,
            "status_code": response.status_code,
            "content_type": content_type,
            "is_available": response.status_code != 404
        }
    except Exception as e:
        print(f"  Error: {str(e)}")
        return {
            "endpoint": endpoint,
            "status_code": None,
            "error": str(e),
            "is_available": False
        }

# Test results
results = []
print(f"Testing Hokusai API endpoints at {BASE_URL}")
print(f"Time: {datetime.now().isoformat()}")
print("=" * 80)

# Test MLflow endpoints (as documented)
mlflow_endpoints = [
    ("GET", "/api/mlflow/api/2.0/mlflow/experiments/search", "MLflow Experiments Search"),
    ("POST", "/api/mlflow/api/2.0/mlflow/runs/create", "MLflow Create Run", {"experiment_id": "0"}),
    ("POST", "/api/mlflow/api/2.0/mlflow/model-versions/create", "MLflow Create Model Version", {
        "name": "test-model",
        "source": "runs:/fake-run-id/model"
    }),
    ("GET", "/api/mlflow/api/2.0/mlflow/experiments/get-by-name?experiment_name=Default", "MLflow Get Experiment by Name"),
]

# Test direct API endpoints (from third-party guide)
direct_endpoints = [
    ("POST", "/api/models/register", "Direct Model Registration", {
        "model_name": "test-model",
        "model_type": "classification"
    }),
    ("GET", "/api/models", "List Models"),
]

# Test health endpoints
health_endpoints = [
    ("GET", "/api/health/mlflow", "MLflow Health Check"),
    ("GET", "/api/health/mlflow/detailed", "MLflow Detailed Health Check"),
    ("GET", "/api/health", "General Health Check"),
]

# Alternative URLs to test
alternative_bases = [
    ("GET", "/mlflow/api/2.0/mlflow/experiments/search", "MLflow without /api prefix"),
    ("GET", "/api/2.0/mlflow/experiments/search", "MLflow with single /api prefix"),
]

print("\n### Testing MLflow Endpoints ###")
for method, endpoint, desc, *args in mlflow_endpoints:
    data = args[0] if args else None
    result = test_endpoint(method, endpoint, desc, data)
    results.append(result)

print("\n### Testing Direct API Endpoints ###")
for method, endpoint, desc, *args in direct_endpoints:
    data = args[0] if args else None
    result = test_endpoint(method, endpoint, desc, data)
    results.append(result)

print("\n### Testing Health Endpoints ###")
for method, endpoint, desc in health_endpoints:
    result = test_endpoint(method, endpoint, desc)
    results.append(result)

print("\n### Testing Alternative URL Patterns ###")
for method, endpoint, desc in alternative_bases:
    result = test_endpoint(method, endpoint, desc)
    results.append(result)

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

available = [r for r in results if r.get('is_available')]
unavailable = [r for r in results if not r.get('is_available')]

print(f"\nAvailable endpoints: {len(available)}")
for r in available:
    print(f"  ✓ {r['endpoint']} ({r['status_code']})")

print(f"\nUnavailable endpoints: {len(unavailable)}")
for r in unavailable:
    print(f"  ✗ {r['endpoint']} ({r.get('status_code', 'Error')})")

# Save detailed results
report = {
    "test_time": datetime.now().isoformat(),
    "base_url": BASE_URL,
    "total_tested": len(results),
    "available": len(available),
    "unavailable": len(unavailable),
    "results": results
}

with open("endpoint_availability_report.json", "w") as f:
    json.dump(report, f, indent=2)

print(f"\nDetailed report saved to: endpoint_availability_report.json")