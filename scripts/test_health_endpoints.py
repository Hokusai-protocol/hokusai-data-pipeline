#!/usr/bin/env python3
"""Test health check endpoints from PR #60."""

import requests
import sys
import json
from datetime import datetime

# Configuration
API_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
API_KEY = sys.argv[2] if len(sys.argv) > 2 else "test-api-key"


def test_mlflow_health():
    """Test the MLflow health check endpoint."""
    print(f"\n🏥 Testing MLflow Health Check Endpoint")
    print("=" * 60)
    
    try:
        response = requests.get(
            f"{API_URL}/mlflow/health/mlflow",
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Overall Status: {data.get('status', 'unknown')}")
            print(f"MLflow Server: {data.get('mlflow_server', 'unknown')}")
            
            print("\nHealth Checks:")
            for check_name, check_data in data.get('checks', {}).items():
                status = check_data.get('status', 'unknown')
                message = check_data.get('message', '')
                emoji = "✅" if status in ["healthy", "enabled"] else "❌" if status == "unhealthy" else "⚠️"
                print(f"  {emoji} {check_name}: {status} - {message}")
            
            return data.get('status') == 'healthy'
        else:
            print(f"❌ Health check failed with status {response.status_code}")
            if response.text:
                print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_mlflow_detailed_health():
    """Test the detailed MLflow health check endpoint."""
    print(f"\n🔍 Testing Detailed MLflow Health Check")
    print("=" * 60)
    
    try:
        response = requests.get(
            f"{API_URL}/mlflow/health/mlflow/detailed",
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Overall Health: {'✅ Healthy' if data.get('overall_health') else '❌ Unhealthy'}")
            print(f"Timestamp: {data.get('timestamp', 'unknown')}")
            
            print("\nEnvironment:")
            for key, value in data.get('environment', {}).items():
                print(f"  {key}: {value}")
            
            print("\nEndpoint Tests:")
            for test in data.get('tests', []):
                emoji = "✅" if test.get('success') else "❌"
                print(f"  {emoji} {test.get('endpoint')}: {test.get('status_code', 'N/A')}")
                if 'response_time_ms' in test:
                    print(f"     Response time: {test['response_time_ms']:.2f}ms")
                if 'error' in test:
                    print(f"     Error: {test['error']}")
            
            return data.get('overall_health', False)
        else:
            print(f"❌ Detailed health check failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_api_health():
    """Test the main API health check endpoint."""
    print(f"\n💗 Testing Main API Health Check")
    print("=" * 60)
    
    try:
        response = requests.get(
            f"{API_URL}/health",
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status', 'unknown')}")
            print(f"Timestamp: {data.get('timestamp', 'unknown')}")
            
            if 'services' in data:
                print("\nServices:")
                for service, status in data.get('services', {}).items():
                    emoji = "✅" if status == 'connected' else "❌"
                    print(f"  {emoji} {service}: {status}")
            
            return data.get('status') == 'healthy'
        else:
            print(f"❌ API health check failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all health check tests."""
    print(f"\n🏥 Health Check Endpoint Tests - {datetime.now()}")
    print(f"API URL: {API_URL}")
    print("-" * 60)
    
    results = []
    
    # Test main API health
    results.append(("API Health", test_api_health()))
    
    # Test MLflow health endpoints
    results.append(("MLflow Health", test_mlflow_health()))
    results.append(("MLflow Detailed Health", test_mlflow_detailed_health()))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        emoji = "✅" if result else "❌"
        print(f"  {emoji} {name}: {'PASS' if result else 'FAIL'}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All health check endpoints are working correctly!")
        return 0
    else:
        print("❌ Some health check endpoints failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())