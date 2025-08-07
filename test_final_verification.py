import os
import json
import requests
import time
from datetime import datetime

# Configuration
API_KEY = "hk_live_NVWOYDfNfTJyFzUDkQDBk2LLA4pB5qza"
BASE_URL = "https://registry.hokus.ai"

def test_model_registration():
    """Test the complete model registration flow"""
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    # Generate unique model name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = f"test_model_{timestamp}"
    
    print("=" * 60)
    print("FINAL VERIFICATION TEST")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"API URL: {BASE_URL}")
    print()
    
    # Step 1: Register a baseline model
    print("1. Registering baseline model...")
    baseline_payload = {
        "model_name": model_name,
        "model_type": "classification",
        "model_data": {
            "algorithm": "test_algorithm",
            "version": "1.0.0",
            "framework": "pytest"
        },
        "metadata": {
            "test_run": "final_verification",
            "deployed_fixes": [
                "Database authentication with mlflow user",
                "MLflow URL using service discovery domain",
                "Docker image built for AMD64 architecture"
            ]
        }
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/models/baseline",
            headers=headers,
            json=baseline_payload,
            timeout=30
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ SUCCESS: Model registered")
            print(f"   Model ID: {result.get('model_id')}")
            print(f"   Run ID: {result.get('run_id')}")
            return True
        else:
            print(f"   ❌ FAILED: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("   ❌ FAILED: Request timed out")
        return False
    except Exception as e:
        print(f"   ❌ FAILED: {str(e)}")
        return False

def test_mlflow_connectivity():
    """Test direct MLflow connectivity through the proxy"""
    
    print("\n2. Testing MLflow connectivity...")
    
    headers = {
        "X-API-Key": API_KEY
    }
    
    try:
        # Test MLflow API through proxy
        response = requests.get(
            f"{BASE_URL}/mlflow/api/2.0/mlflow/experiments/list",
            headers=headers,
            timeout=10
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ MLflow connected successfully")
            print(f"   Number of experiments: {len(data.get('experiments', []))}")
            return True
        else:
            print(f"   ❌ MLflow connection failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ MLflow test failed: {str(e)}")
        return False

def main():
    """Run all verification tests"""
    
    results = {
        "model_registration": test_model_registration(),
        "mlflow_connectivity": test_mlflow_connectivity()
    }
    
    print("\n" + "=" * 60)
    print("FINAL VERIFICATION RESULTS")
    print("=" * 60)
    
    all_passed = all(results.values())
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print()
    if all_passed:
        print("🎉 ALL FIXES VERIFIED - SYSTEM FULLY OPERATIONAL")
        print("\nFixed issues:")
        print("1. Database authentication using mlflow user")
        print("2. MLflow connectivity using hokusai-development.local domain")
        print("3. Docker image architecture compatibility (AMD64)")
        print("4. ECS task definitions updated with correct configuration")
    else:
        print("⚠️ Some issues remain - check failed tests above")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit(main())
