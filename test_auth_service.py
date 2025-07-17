#!/usr/bin/env python3
"""
Test the authentication service directly to debug why the API key is rejected.
"""

import requests
import json
import os

def test_auth_service():
    """Test authentication service directly."""
    
    api_key = "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
    auth_url = "https://auth.hokus.ai/api/v1/keys/validate"
    
    print("=" * 70)
    print("AUTHENTICATION SERVICE TEST")
    print("=" * 70)
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"Auth URL: {auth_url}")
    
    # Test 1: Direct validation request
    print("\n1. Testing direct validation request...")
    
    payload = {
        "api_key": api_key,
        "client_ip": "127.0.0.1",
        "service_id": "ml-platform"
    }
    
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            auth_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        try:
            response_data = response.json()
            print(f"Response Body: {json.dumps(response_data, indent=2)}")
        except:
            print(f"Response Text: {response.text}")
            
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 2: Try different service IDs
    print("\n2. Testing different service IDs...")
    
    service_ids = ["ml-platform", "api", "mlflow", "hokusai", None]
    
    for service_id in service_ids:
        payload = {
            "api_key": api_key,
            "client_ip": "127.0.0.1"
        }
        if service_id:
            payload["service_id"] = service_id
            
        try:
            response = requests.post(auth_url, json=payload, timeout=5)
            print(f"  service_id={service_id}: {response.status_code}")
            if response.status_code != 401:
                print(f"    Response: {response.text[:100]}")
        except Exception as e:
            print(f"  service_id={service_id}: Error - {e}")
    
    # Test 3: Check if it's an authorization header issue
    print("\n3. Testing with Bearer token in header...")
    
    try:
        response = requests.post(
            auth_url,
            json={"service_id": "ml-platform"},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5
        )
        print(f"Bearer header: {response.status_code}")
        if response.status_code != 401:
            print(f"  Response: {response.text[:100]}")
    except Exception as e:
        print(f"Bearer header: Error - {e}")
    
    # Test 4: Try the public endpoints to see format
    print("\n4. Checking public endpoints...")
    
    # Try health endpoint
    try:
        response = requests.get("https://auth.hokus.ai/health", timeout=5)
        print(f"Health endpoint: {response.status_code}")
    except:
        pass
    
    # Try root
    try:
        response = requests.get("https://auth.hokus.ai/", timeout=5)
        print(f"Root endpoint: {response.status_code}")
        if response.status_code == 200:
            print(f"  Response: {response.text[:200]}")
    except:
        pass


if __name__ == "__main__":
    test_auth_service()