#\!/usr/bin/env python3
import os
import requests
import json

API_KEY = os.environ.get("HOKUSAI_API_KEY", "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL")
AUTH_URL = "https://auth.hokus.ai/api/v1/keys/validate"

print("Testing auth service with service_id='platform'")
print(f"API Key: {API_KEY[:10]}...{API_KEY[-4:]}")
print(f"Auth URL: {AUTH_URL}\n")

# Test with service_id="platform"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "service_id": "platform",
    "client_ip": "127.0.0.1"
}

print("Request:")
print(f"Headers: {headers}")
print(f"Payload: {json.dumps(payload, indent=2)}\n")

try:
    response = requests.post(AUTH_URL, headers=headers, json=payload, timeout=10)
    print(f"Response Status: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print(f"Response Body: {response.text}\n")
    
    if response.status_code == 200:
        print("✅ SUCCESS: Authentication validated with service_id='platform'\!")
    else:
        print(f"❌ FAILED: Status {response.status_code}")
except Exception as e:
    print(f"❌ ERROR: {e}")

# Also test without Bearer prefix
print("\nTesting with X-API-Key header and service_id='platform':")
headers2 = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

try:
    response2 = requests.post(AUTH_URL, headers=headers2, json=payload, timeout=10)
    print(f"Response Status: {response2.status_code}")
    if response2.status_code == 200:
        print("✅ SUCCESS with X-API-Key header\!")
    else:
        print(f"Response: {response2.text}")
except Exception as e:
    print(f"❌ ERROR: {e}")
