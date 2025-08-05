#!/usr/bin/env python3
"""
Script to create a platform API key for MLflow testing
"""

import httpx
import json
import sys
import os

# Configuration
BASE_URL = "https://auth.hokus.ai"
ADMIN_TOKEN = "88IngITCxCtEszifFTh24gPG9hv2owe9"

def create_api_key():
    """Create a new platform API key."""
    
    # Key configuration for platform access
    key_data = {
        "name": "Platform MLflow Test Key",
        "service_id": "platform",
        "environment": "production",
        "rate_limit_per_hour": 10000,
        "billing_plan": "pro",
        "scopes": ["read", "write"]
    }
    
    # Make the request
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    
    try:
        print("Creating Platform API Key...")
        print("=" * 60)
        
        with httpx.Client() as client:
            response = client.post(
                f"{BASE_URL}/api/v1/keys",
                json=key_data,
                headers=headers,
                timeout=30.0
            )
            
            response.raise_for_status()
            result = response.json()
            
            print("✅ API Key created successfully!")
            print("\n" + "="*60)
            print(f"API Key: {result['api_key']}")
            print("="*60)
            print("\n⚠️  IMPORTANT: Save this API key securely. It will not be shown again!")
            
            print("\nKey Details:")
            key_info = result['key_info']
            print(f"  - Key ID: {key_info['key_id']}")
            print(f"  - Name: {key_info['name']}")
            print(f"  - Service: {key_info['service_id']}")
            print(f"  - Environment: {key_info['environment']}")
            print(f"  - Rate Limit: {key_info['rate_limit_per_hour']} requests/hour")
            print(f"  - Billing Plan: {key_info['billing_plan']}")
            
            if key_info.get('scopes'):
                print(f"  - Scopes: {', '.join(key_info['scopes'])}")
            
            # Save to environment variable suggestion
            print("\nTo use this key:")
            print(f"export HOKUSAI_API_KEY=\"{result['api_key']}\"")
                
            return result['api_key']
            
    except httpx.HTTPStatusError as e:
        print(f"❌ Error creating API key: {e.response.status_code}")
        print(f"Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    api_key = create_api_key()