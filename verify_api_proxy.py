#!/usr/bin/env python3
"""Verify that the Hokusai API proxy is deployed and working correctly."""

import os
import sys
import requests
import json
from datetime import datetime

def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'=' * 70}")
    print(f"{title}")
    print(f"{'=' * 70}")

def check_endpoint(url, headers=None, description=""):
    """Check if an endpoint is accessible."""
    print(f"\n{description}")
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✓ SUCCESS")
            return True, response
        elif response.status_code == 401:
            print("✗ Authentication required")
            return False, response
        elif response.status_code == 403:
            print("✗ Forbidden - authentication failed")
            return False, response
        elif response.status_code == 404:
            print("✗ Not Found - endpoint doesn't exist")
            return False, response
        elif response.status_code == 502:
            print("✗ Bad Gateway - backend service unavailable")
            return False, response
        else:
            print(f"✗ Unexpected status code")
            return False, response
            
    except requests.exceptions.Timeout:
        print("✗ Request timed out")
        return False, None
    except requests.exceptions.ConnectionError:
        print("✗ Connection failed")
        return False, None
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False, None

def main():
    """Main verification script."""
    print_section("HOKUSAI API PROXY VERIFICATION")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Get API key from environment
    api_key = os.getenv("HOKUSAI_API_KEY")
    if not api_key:
        print("\n❌ ERROR: HOKUSAI_API_KEY environment variable not set")
        print("Please set: export HOKUSAI_API_KEY='your-api-key'")
        sys.exit(1)
    
    print(f"\nAPI Key: {api_key[:10]}...{api_key[-4:]}")
    
    # Test endpoints
    base_url = "https://registry.hokus.ai"
    
    print_section("1. INFRASTRUCTURE HEALTH CHECKS")
    
    # Check API service health
    success, _ = check_endpoint(
        f"{base_url}/health",
        description="API Service Health Check"
    )
    
    # Check if API routes are working
    success, _ = check_endpoint(
        f"{base_url}/api/health",
        description="API Routes Health Check"
    )
    
    print_section("2. AUTHENTICATION TESTS")
    
    # Test authentication with Bearer token
    headers = {"Authorization": f"Bearer {api_key}"}
    
    # Test a protected endpoint
    success, response = check_endpoint(
        f"{base_url}/api/models",
        headers=headers,
        description="Test Bearer Token Authentication"
    )
    
    if success and response:
        print("✓ Bearer token authentication is working!")
    
    print_section("3. MLFLOW PROXY TESTS")
    
    # Check if MLflow proxy endpoint exists
    proxy_url = f"{base_url}/api/mlflow"
    
    # Test MLflow proxy health
    success, _ = check_endpoint(
        f"{proxy_url}/health/mlflow",
        headers=headers,
        description="MLflow Proxy Health Check"
    )
    
    # Test MLflow experiments endpoint through proxy
    success, response = check_endpoint(
        f"{proxy_url}/api/2.0/mlflow/experiments/search",
        headers=headers,
        description="MLflow Experiments API (via proxy)"
    )
    
    if success and response:
        print("✓ MLflow proxy is working correctly!")
        try:
            data = response.json()
            print(f"  Found {len(data.get('experiments', []))} experiments")
        except:
            pass
    
    print_section("4. DIRECT MLFLOW ACCESS (for comparison)")
    
    # Test direct MLflow access
    direct_url = f"{base_url}/mlflow"
    success, _ = check_endpoint(
        f"{direct_url}/api/2.0/mlflow/experiments/search",
        description="Direct MLflow Access (no auth)"
    )
    
    print_section("VERIFICATION SUMMARY")
    
    # Test with MLflow Python client
    print("\nTo test with MLflow Python client, run:")
    print("```python")
    print("import os")
    print("import mlflow")
    print("")
    print(f'os.environ["MLFLOW_TRACKING_URI"] = "{proxy_url}"')
    print(f'os.environ["MLFLOW_TRACKING_TOKEN"] = "{api_key}"')
    print("")
    print("client = mlflow.tracking.MlflowClient()")
    print("experiments = client.search_experiments()")
    print("print(f'Found {len(experiments)} experiments')")
    print("```")
    
    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()