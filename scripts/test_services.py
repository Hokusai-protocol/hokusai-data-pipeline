#!/usr/bin/env python3
"""Test Hokusai API and MLflow services are working properly."""

import requests
import json
import sys
from typing import Dict, List, Tuple

# Service endpoints
SERVICES = {
    "API": {
        "base_url": "http://hokusai-development-794046971.us-east-1.elb.amazonaws.com",
        "endpoints": [
            ("/api/health", "GET", None),
            ("/api/v1/health", "GET", None),
            ("/api/v1/models", "GET", None),
            ("/api/v1/runs", "GET", None),
        ]
    },
    "MLflow": {
        "base_url": "http://hokusai-development-794046971.us-east-1.elb.amazonaws.com",
        "endpoints": [
            ("/mlflow/health", "GET", None),
            ("/mlflow/api/2.0/mlflow/experiments/search", "GET", None),
            ("/mlflow/api/2.0/mlflow/registered-models/search", "GET", None),
        ]
    }
}

def test_endpoint(base_url: str, endpoint: str, method: str, data: Dict = None) -> Tuple[bool, str, int]:
    """Test a single endpoint."""
    url = f"{base_url}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=10, allow_redirects=False)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10, allow_redirects=False)
        else:
            return False, f"Unsupported method: {method}", 0
        
        # Check for redirects
        if response.status_code in [301, 302, 307, 308]:
            return False, f"Redirect to: {response.headers.get('Location', 'unknown')}", response.status_code
        
        # Check if successful
        success = response.status_code < 400
        
        # Try to get response content
        try:
            content = response.json()
            message = json.dumps(content, indent=2)
        except:
            content = response.text[:200]
            message = content if content else "No content"
            
        return success, message, response.status_code
        
    except requests.exceptions.ConnectionError as e:
        return False, f"Connection error: {str(e)}", 0
    except requests.exceptions.Timeout:
        return False, "Request timeout", 0
    except Exception as e:
        return False, f"Error: {str(e)}", 0

def main():
    """Test all services and endpoints."""
    print("🔍 Testing Hokusai Services\n")
    
    all_passed = True
    
    for service_name, service_config in SERVICES.items():
        print(f"\n{'='*60}")
        print(f"Testing {service_name} Service")
        print(f"Base URL: {service_config['base_url']}")
        print(f"{'='*60}\n")
        
        passed = 0
        failed = 0
        
        for endpoint, method, data in service_config['endpoints']:
            success, message, status_code = test_endpoint(
                service_config['base_url'], 
                endpoint, 
                method, 
                data
            )
            
            status_emoji = "✅" if success else "❌"
            status_text = f"[{status_code}]" if status_code else "[ERR]"
            
            print(f"{status_emoji} {method} {endpoint} {status_text}")
            if not success or True:  # Always show details for debugging
                print(f"   Response: {message[:200]}")
            print()
            
            if success:
                passed += 1
            else:
                failed += 1
                all_passed = False
        
        print(f"\nSummary for {service_name}: {passed} passed, {failed} failed")
    
    print(f"\n{'='*60}")
    print(f"Overall Result: {'✅ All tests passed!' if all_passed else '❌ Some tests failed'}")
    print(f"{'='*60}\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())