#!/usr/bin/env python3
"""Verify model registration works with PR #60 deployment."""

import os
import sys
import requests
from datetime import datetime

def test_model_registration():
    # Get credentials
    api_key = os.getenv("HOKUSAI_API_KEY")
    api_url = os.getenv("HOKUSAI_API_URL", "https://registry.hokus.ai")
    
    print(f"\n🧪 Testing Model Registration via Hokusai API")
    print("=" * 60)
    print(f"API URL: {api_url}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    
    # Test creating experiment
    print("\n1️⃣ Creating experiment...")
    experiment_name = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    response = requests.post(
        f"{api_url}/api/mlflow/api/2.0/mlflow/experiments/create",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"name": experiment_name}
    )
    
    if response.status_code == 200:
        exp_id = response.json()["experiment_id"]
        print(f"   ✅ Created experiment: {experiment_name} (ID: {exp_id})")
    else:
        print(f"   ❌ Failed: {response.status_code} - {response.text}")
        return False
    
    # Test creating run
    print("\n2️⃣ Creating run...")
    response = requests.post(
        f"{api_url}/api/mlflow/api/2.0/mlflow/runs/create",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"experiment_id": exp_id}
    )
    
    if response.status_code == 200:
        run_id = response.json()["run"]["info"]["run_id"]
        print(f"   ✅ Created run: {run_id}")
    else:
        print(f"   ❌ Failed: {response.status_code}")
        return False
    
    # Test logging metrics
    print("\n3️⃣ Logging metrics...")
    response = requests.post(
        f"{api_url}/api/mlflow/api/2.0/mlflow/runs/log-metric",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "run_id": run_id,
            "key": "accuracy",
            "value": 0.95,
            "timestamp": int(datetime.now().timestamp() * 1000)
        }
    )
    
    if response.status_code == 200:
        print(f"   ✅ Logged metrics successfully")
    else:
        print(f"   ❌ Failed: {response.status_code}")
        return False
    
    # Test model registration
    print("\n4️⃣ Registering model...")
    model_name = f"test-model-{int(datetime.now().timestamp())}"
    
    response = requests.post(
        f"{api_url}/api/mlflow/api/2.0/mlflow/registered-models/create",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"name": model_name}
    )
    
    if response.status_code == 200:
        print(f"   ✅ Registered model: {model_name}")
    else:
        print(f"   ❌ Failed: {response.status_code} - {response.text}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ SUCCESS: Model registration completed!")
    print("✅ PR #60 MLflow proxy routing is working correctly!")
    print("\nThe MLflow proxy at /api/mlflow/* is properly routing requests.")
    return True

if __name__ == "__main__":
    if test_model_registration():
        sys.exit(0)
    else:
        sys.exit(1)