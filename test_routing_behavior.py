#!/usr/bin/env python3
"""
Test script to verify routing behavior for MLflow proxy endpoints.
This script tests both the current (broken) state and the expected (fixed) state.
"""

import os
import sys
import requests
from typing import Optional, Tuple
import json

# Configuration
API_KEY = os.getenv("HOKUSAI_API_KEY", "")
BASE_URL = os.getenv("HOKUSAI_BASE_URL", "http://registry.hokus.ai")

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def test_endpoint(url: str, headers: Optional[dict] = None, description: str = "") -> Tuple[bool, dict]:
    """Test an endpoint and return success status and response details."""
    if not description:
        description = url
    
    print(f"\n{BLUE}Testing: {description}{RESET}")
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        status_code = response.status_code
        
        # Try to get response body
        try:
            body = response.json()
        except:
            body = {"text": response.text[:200]}
        
        # Determine success
        success = status_code in [200, 401]  # 401 is expected without auth
        
        # Color code the result
        if success:
            if status_code == 200:
                print(f"{GREEN}✓ Status: {status_code} - Success{RESET}")
            else:
                print(f"{YELLOW}! Status: {status_code} - Auth Required{RESET}")
        else:
            print(f"{RED}✗ Status: {status_code} - Failed{RESET}")
        
        # Print relevant response details
        if status_code == 404:
            print(f"  {RED}Not Found - Route doesn't exist{RESET}")
        elif status_code == 502:
            print(f"  {RED}Bad Gateway - Backend connection failed{RESET}")
        elif status_code == 504:
            print(f"  {RED}Gateway Timeout - Backend timeout{RESET}")
        
        return success, {"status": status_code, "body": body}
        
    except requests.exceptions.Timeout:
        print(f"{RED}✗ Request timed out{RESET}")
        return False, {"error": "timeout"}
    except requests.exceptions.ConnectionError as e:
        print(f"{RED}✗ Connection error: {e}{RESET}")
        return False, {"error": "connection"}
    except Exception as e:
        print(f"{RED}✗ Unexpected error: {e}{RESET}")
        return False, {"error": str(e)}


def main():
    """Run routing tests."""
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Hokusai API Routing Test{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    
    if not API_KEY:
        print(f"{YELLOW}Warning: HOKUSAI_API_KEY not set{RESET}")
        print("Some tests may fail due to authentication")
        print("Set: export HOKUSAI_API_KEY='your_key_here'")
    
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    
    # Test categories
    print(f"\n{BLUE}1. Current State - Testing Routing Conflicts{RESET}")
    print("-" * 50)
    
    # This should fail with current routing (goes to API, not MLflow)
    test_endpoint(
        f"{BASE_URL}/api/mlflow/api/2.0/mlflow/experiments/search",
        headers,
        "/api/mlflow/* path (BROKEN - caught by /api* rule)"
    )
    
    # This works as a workaround
    test_endpoint(
        f"{BASE_URL}/mlflow/api/2.0/mlflow/experiments/search",
        headers,
        "/mlflow/* path (WORKING - current workaround)"
    )
    
    print(f"\n{BLUE}2. API Endpoints - Verify Existing Routes Work{RESET}")
    print("-" * 50)
    
    # Test versioned API endpoints
    test_endpoint(
        f"{BASE_URL}/api/v1/dspy/health",
        headers,
        "DSPy API endpoint"
    )
    
    test_endpoint(
        f"{BASE_URL}/models",
        headers,
        "Models API endpoint"
    )
    
    test_endpoint(
        f"{BASE_URL}/health",
        None,  # No auth needed
        "Health check endpoint"
    )
    
    print(f"\n{BLUE}3. Auth Service - Critical to Verify{RESET}")
    print("-" * 50)
    
    # Test auth service endpoints
    test_endpoint(
        "https://auth.hokus.ai/api/v1/keys/validate",
        None,
        "Auth service validation endpoint"
    )
    
    test_endpoint(
        "https://auth.hokus.ai/",
        None,
        "Auth service root"
    )
    
    print(f"\n{BLUE}4. MLflow Direct Access{RESET}")
    print("-" * 50)
    
    # Direct MLflow access (if available)
    test_endpoint(
        f"{BASE_URL}/mlflow/ajax-api/2.0/mlflow/experiments/search",
        None,
        "Direct MLflow access (ajax-api)"
    )
    
    print(f"\n{BLUE}4. Expected Behavior After Fix{RESET}")
    print("-" * 50)
    
    print(f"\n{YELLOW}After deploying the routing fix:{RESET}")
    print("1. /api/mlflow/* paths will work correctly")
    print("2. Standard MLflow client configuration will work:")
    print(f'   {GREEN}export MLFLOW_TRACKING_URI="{BASE_URL}/api/mlflow"{RESET}')
    print(f'   {GREEN}export MLFLOW_TRACKING_TOKEN="{API_KEY}"{RESET}')
    
    # Test if the fix is deployed
    print(f"\n{BLUE}5. Testing if Fix is Deployed{RESET}")
    print("-" * 50)
    
    success, result = test_endpoint(
        f"{BASE_URL}/api/mlflow/health/mlflow",
        headers,
        "MLflow health via /api/mlflow (indicates fix is deployed)"
    )
    
    if success and result.get("status") == 200:
        print(f"\n{GREEN}✓ ROUTING FIX IS DEPLOYED!{RESET}")
        print("Standard MLflow paths are now working correctly.")
    else:
        print(f"\n{YELLOW}! Routing fix not yet deployed{RESET}")
        print("Use the workaround: MLFLOW_TRACKING_URI='http://registry.hokus.ai/mlflow'")
    
    print(f"\n{BLUE}Summary{RESET}")
    print("-" * 50)
    print("Current routing conflict: /api* catches all /api/mlflow/* requests")
    print("Workaround: Use /mlflow/* paths directly")
    print("Fix: Deploy routing-fix.tf to make ALB rules more specific")


if __name__ == "__main__":
    main()