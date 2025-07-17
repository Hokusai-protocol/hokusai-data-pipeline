#!/usr/bin/env python3
"""
Test auth service endpoints to understand the API.
"""

import requests
import json

def test_auth_endpoints():
    """Test various auth service endpoints to understand the API."""
    print("="*70)
    print("AUTH SERVICE ENDPOINT DISCOVERY")
    print("="*70)
    
    base_url = "https://auth.hokus.ai"
    api_key = "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
    
    # Test 1: Check available endpoints
    print("\n1. Testing root and common endpoints...")
    endpoints = [
        "/",
        "/api",
        "/api/v1",
        "/api/v1/keys",
        "/api/v1/auth",
        "/api/v1/validate",
        "/api/v1/verify",
        "/health",
        "/status",
        "/docs",
        "/openapi.json"
    ]
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        try:
            response = requests.get(url, timeout=5)
            print(f"{endpoint}: {response.status_code} - {response.text[:100] if response.text else 'empty'}")
        except Exception as e:
            print(f"{endpoint}: ERROR - {str(e)}")
    
    # Test 2: Try different validation endpoints with GET
    print("\n2. Testing validation endpoints with GET...")
    validation_endpoints = [
        f"/api/v1/keys/validate/{api_key}",
        f"/api/v1/keys/{api_key}/validate",
        f"/api/v1/validate/{api_key}",
        f"/api/v1/auth/validate/{api_key}",
    ]
    
    for endpoint in validation_endpoints:
        url = f"{base_url}{endpoint}"
        try:
            response = requests.get(url, timeout=5)
            print(f"{endpoint}: {response.status_code}")
            if response.status_code != 404:
                print(f"  Response: {response.text[:200]}")
        except Exception as e:
            print(f"{endpoint}: ERROR - {str(e)}")
    
    # Test 3: Check if the API expects different authentication methods
    print("\n3. Testing different authentication methods on /api/v1/keys/validate...")
    
    # Method A: API key in URL parameter
    try:
        response = requests.post(
            f"{base_url}/api/v1/keys/validate?api_key={api_key}",
            json={"service_id": "ml-platform"},
            timeout=5
        )
        print(f"API key in URL param: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"API key in URL param: ERROR - {str(e)}")
    
    # Method B: API key in JSON body (original method before fix)
    try:
        response = requests.post(
            f"{base_url}/api/v1/keys/validate",
            json={
                "api_key": api_key,
                "service_id": "ml-platform"
            },
            timeout=5
        )
        print(f"\nAPI key in JSON body: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"API key in JSON body: ERROR - {str(e)}")
    
    # Method C: Check if it's a simple GET endpoint
    try:
        response = requests.get(
            f"{base_url}/api/v1/keys/validate",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5
        )
        print(f"\nGET with Bearer token: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"GET with Bearer token: ERROR - {str(e)}")

if __name__ == "__main__":
    test_auth_endpoints()