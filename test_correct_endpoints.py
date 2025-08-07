import os
import json
import requests
from datetime import datetime

# Configuration
API_KEY = "hk_live_NVWOYDfNfTJyFzUDkQDBk2LLA4pB5qza"
BASE_URL = "https://registry.hokus.ai"

def test_endpoints():
    """Test available endpoints"""
    
    headers = {
        "X-API-Key": API_KEY
    }
    
    print("=" * 60)
    print("TESTING AVAILABLE ENDPOINTS")
    print("=" * 60)
    
    # Test health endpoint
    print("\n1. Health endpoint:")
    response = requests.get(f"{BASE_URL}/health", headers=headers, timeout=10)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   MLflow: {data['services']['mlflow']}")
        print(f"   Postgres: {data['services']['postgres']}")
    
    # Test models list endpoint
    print("\n2. Models list endpoint:")
    response = requests.get(f"{BASE_URL}/models", headers=headers, timeout=10)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Response: {data}")
    
    # Test model registration endpoint (POST /models)
    print("\n3. Model registration endpoint:")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "model_name": f"test_model_{timestamp}",
        "model_type": "classification",
        "model_data": {
            "algorithm": "test",
            "version": "1.0.0"
        },
        "metadata": {
            "test": "verification"
        }
    }
    
    headers["Content-Type"] = "application/json"
    response = requests.post(f"{BASE_URL}/models", headers=headers, json=payload, timeout=30)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ Model registration successful\!")
        data = response.json()
        print(f"   Model ID: {data.get('model_id')}")
    else:
        print(f"   Response: {response.text}")
    
    # Test MLflow proxy
    print("\n4. MLflow proxy endpoint:")
    response = requests.get(f"{BASE_URL}/api/mlflow/experiments/list", headers=headers, timeout=10)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ MLflow proxy working\!")

if __name__ == "__main__":
    test_endpoints()
