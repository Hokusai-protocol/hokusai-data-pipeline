#\!/usr/bin/env python3
import os
import requests
import json

API_KEY = os.environ.get("HOKUSAI_API_KEY", "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL")
PROXY_URL = "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search"

print("Testing proxy with updated service_id knowledge")
print(f"API Key: {API_KEY[:10]}...{API_KEY[-4:]}")
print(f"Proxy URL: {PROXY_URL}\n")

# Test 1: Standard Bearer token
print("Test 1: Bearer token in Authorization header")
headers1 = {
    "Authorization": f"Bearer {API_KEY}",
    "X-Service-Id": "platform"  # Try including service ID in header
}
try:
    response1 = requests.get(PROXY_URL, headers=headers1, timeout=10)
    print(f"Status: {response1.status_code}")
    print(f"Response: {response1.text}\n")
except Exception as e:
    print(f"Error: {e}\n")

# Test 2: Direct health check
print("Test 2: Testing registry health endpoint")
health_url = "https://registry.hokus.ai/health"
try:
    response2 = requests.get(health_url, timeout=10)
    print(f"Status: {response2.status_code}")
    print(f"Response: {response2.text}\n")
except Exception as e:
    print(f"Error: {e}\n")

# Test 3: Check if MLflow is accessible directly  
print("Test 3: Direct MLflow ajax-api endpoint")
mlflow_direct = "https://registry.hokus.ai/mlflow/ajax-api/2.0/mlflow/experiments/search?max_results=1"
try:
    response3 = requests.get(mlflow_direct, timeout=10)
    print(f"Status: {response3.status_code}")
    print(f"Response: {response3.text[:200]}...\n")
except Exception as e:
    print(f"Error: {e}\n")

# Test 4: Try the API without /mlflow path
print("Test 4: API models endpoint")
models_url = "https://registry.hokus.ai/api/models"
headers4 = {
    "Authorization": f"Bearer {API_KEY}"
}
try:
    response4 = requests.get(models_url, headers=headers4, timeout=10)
    print(f"Status: {response4.status_code}")
    print(f"Response: {response4.text}\n")
except Exception as e:
    print(f"Error: {e}\n")
