#!/usr/bin/env python3
"""Test the new health check endpoints at /api/health/mlflow."""

import requests
import sys
import json
from datetime import datetime

def test_health_endpoints(api_url="http://localhost:8001", api_key=None):
    """Test all MLflow health check endpoints."""
    
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    print(f"\n🧪 Testing New MLflow Health Check Endpoints")
    print(f"Time: {datetime.now()}")
    print(f"API URL: {api_url}")
    print("=" * 60)
    
    endpoints = [
        {
            "name": "Basic Health Check",
            "path": "/api/health/mlflow",
            "description": "Overall MLflow health status"
        },
        {
            "name": "Detailed Health Check",
            "path": "/api/health/mlflow/detailed",
            "description": "Comprehensive endpoint testing"
        },
        {
            "name": "Connectivity Check",
            "path": "/api/health/mlflow/connectivity",
            "description": "Simple connectivity test"
        }
    ]
    
    results = []
    
    for endpoint in endpoints:
        print(f"\n📍 {endpoint['name']}")
        print(f"   Path: {endpoint['path']}")
        print(f"   Description: {endpoint['description']}")
        
        try:
            response = requests.get(
                f"{api_url}{endpoint['path']}",
                headers=headers,
                timeout=10
            )
            
            print(f"   Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("   Response:")
                print(json.dumps(data, indent=4))
                results.append((endpoint['name'], True, "Success"))
            elif response.status_code == 503:
                # Service unavailable but endpoint exists
                data = response.json()
                print("   Response (Service Unavailable):")
                print(json.dumps(data.get('detail', data), indent=4))
                results.append((endpoint['name'], True, "Endpoint exists (service unavailable)"))
            else:
                print(f"   ❌ Unexpected status: {response.status_code}")
                print(f"   Response: {response.text}")
                results.append((endpoint['name'], False, f"Status {response.status_code}"))
                
        except requests.exceptions.ConnectionError:
            print("   ❌ Connection failed - is the API running?")
            results.append((endpoint['name'], False, "Connection failed"))
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append((endpoint['name'], False, str(e)))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    success_count = sum(1 for _, success, _ in results if success)
    total_count = len(results)
    
    for name, success, message in results:
        status = "✅" if success else "❌"
        print(f"   {status} {name}: {message}")
    
    print(f"\nTotal: {success_count}/{total_count} endpoints working")
    
    if success_count == total_count:
        print("✅ All health check endpoints are accessible!")
        return 0
    else:
        print("❌ Some endpoints are not working correctly.")
        return 1

def main():
    """Main function."""
    import os
    
    # Get API URL and key from environment or arguments
    api_url = os.getenv("HOKUSAI_API_URL", "http://localhost:8001")
    api_key = os.getenv("HOKUSAI_API_KEY")
    
    if len(sys.argv) > 1:
        api_url = sys.argv[1]
    if len(sys.argv) > 2:
        api_key = sys.argv[2]
    
    return test_health_endpoints(api_url, api_key)

if __name__ == "__main__":
    sys.exit(main())