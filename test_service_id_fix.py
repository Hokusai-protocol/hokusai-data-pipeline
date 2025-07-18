#!/usr/bin/env python3
"""
Test to verify changing service_id from 'ml-platform' to 'platform' will work.
This confirms the API key will be accepted with the correct service ID.
"""

import os
import requests
import json

def test_service_id_validation():
    """Test different service_id values to find which one works."""
    print("=" * 70)
    print("SERVICE ID VALIDATION TEST")
    print("=" * 70)
    
    api_key = os.getenv("HOKUSAI_API_KEY")
    if not api_key:
        print("❌ No API key found")
        return False
    
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    
    auth_url = "https://auth.hokus.ai/api/v1/keys/validate"
    
    # Test different service IDs
    service_ids = ["ml-platform", "platform", "api", None]
    
    for service_id in service_ids:
        print(f"\nTesting service_id: {service_id}")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        body = {}
        if service_id:
            body["service_id"] = service_id
        body["client_ip"] = "127.0.0.1"
        
        try:
            response = requests.post(auth_url, headers=headers, json=body, timeout=10)
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✓ SUCCESS - Valid for service: {data.get('service_id')}")
                print(f"  User ID: {data.get('user_id')}")
                print(f"  Key ID: {data.get('key_id')}")
                return service_id
            else:
                print(f"  ✗ FAILED - {response.json().get('detail', 'Unknown error')}")
                
        except Exception as e:
            print(f"  ✗ ERROR - {e}")
    
    return None

def main():
    """Run the test and provide recommendations."""
    working_service_id = test_service_id_validation()
    
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    
    if working_service_id == "platform":
        print("✓ CONFIRMED: The API key works with service_id='platform'")
        print("\nTo fix the issue, update line 137 in src/middleware/auth.py:")
        print("  FROM: \"service_id\": \"ml-platform\"")
        print("  TO:   \"service_id\": \"platform\"")
    elif working_service_id:
        print(f"✓ The API key works with service_id='{working_service_id}'")
        print(f"\nUpdate the middleware to use '{working_service_id}' instead of 'ml-platform'")
    else:
        print("❌ The API key doesn't work with any tested service_id")
        print("A new API key may be needed with proper service access")

if __name__ == "__main__":
    main()