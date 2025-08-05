#!/usr/bin/env python3
"""Test MLflow endpoint availability after routing fix"""

import requests
from typing import Dict, Tuple

def test_endpoint(url: str, headers: Dict[str, str] = None) -> Tuple[int, str]:
    """Test an endpoint and return status code and response"""
    try:
        response = requests.get(url, headers=headers, timeout=5)
        return response.status_code, response.text[:200] if response.text else ""
    except Exception as e:
        return 0, str(e)

def main():
    base_url = "https://registry.hokus.ai"
    
    # Test endpoints without auth
    endpoints = [
        "/health",
        "/api/health",
        "/api/mlflow/health",
        "/api/mlflow/api/2.0/mlflow/experiments/search",
        "/api/mlflow/api/2.0/mlflow/experiments/list",
    ]
    
    print("Testing MLflow Endpoints After Routing Fix")
    print("=" * 60)
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        status, response = test_endpoint(url)
        
        if status == 404:
            result = "❌ NOT FOUND - Routing issue"
        elif status == 401:
            result = "✅ WORKING - Auth required"
        elif status == 200:
            result = "✅ WORKING - No auth needed"
        elif status == 500:
            result = "⚠️ SERVER ERROR"
        elif status == 502:
            result = "⚠️ BAD GATEWAY"
        elif status == 503:
            result = "⚠️ SERVICE UNAVAILABLE"
        elif status == 0:
            result = f"❌ CONNECTION ERROR: {response}"
        else:
            result = f"⚠️ STATUS {status}"
        
        print(f"{endpoint:<50} {result}")
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("- 401 responses indicate routing is working (auth required)")
    print("- 404 responses indicate routing issues")
    print("- 200 responses indicate public endpoints")

if __name__ == "__main__":
    main()