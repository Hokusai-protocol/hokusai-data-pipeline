#!/usr/bin/env python3
"""
Quick Start: Train and Register a Model with Hokusai API

This example shows the minimal steps to train and register a model.
"""

import mlflow
import mlflow.sklearn
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score
from eth_account import Account
from eth_account.messages import encode_defunct
import requests
from datetime import datetime


# Configuration
MLFLOW_TRACKING_URI = "http://registry.hokus.ai/mlflow"
API_BASE_URL = "http://registry.hokus.ai/api"

# IMPORTANT: Use a test private key - never commit real keys!
TEST_PRIVATE_KEY = "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def get_auth_headers(private_key: str) -> dict:
    """Generate ETH authentication headers."""
    account = Account.from_key(private_key)
    message = f"Hokusai API Access - {datetime.utcnow().isoformat()}"
    message_hash = encode_defunct(text=message)
    signed = account.sign_message(message_hash)
    
    return {
        "X-ETH-Address": account.address,
        "X-ETH-Message": message,
        "X-ETH-Signature": signed.signature.hex(),
        "Content-Type": "application/json"
    }


def train_and_log_model():
    """Train a simple model and log it to MLflow."""
    # Configure MLflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("third_party_demo")
    
    # Generate synthetic data
    X, y = make_classification(
        n_samples=1000, 
        n_features=20, 
        n_informative=15, 
        n_redundant=5,
        random_state=42
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    with mlflow.start_run() as run:
        # Train model
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        
        # Log to MLflow
        mlflow.log_param("n_estimators", 100)
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1_score", f1)
        mlflow.sklearn.log_model(model, "model")
        
        print(f"✅ Model trained successfully!")
        print(f"   Run ID: {run.info.run_id}")
        print(f"   Accuracy: {accuracy:.3f}")
        print(f"   F1 Score: {f1:.3f}")
        
        return {
            "run_id": run.info.run_id,
            "model_uri": f"runs:/{run.info.run_id}/model",
            "accuracy": accuracy,
            "f1_score": f1
        }


def register_with_hokusai(training_result: dict, private_key: str):
    """Register the model with Hokusai API."""
    headers = get_auth_headers(private_key)
    
    registration_data = {
        "model_name": "demo_classifier",
        "model_type": "classification",
        "mlflow_run_id": training_result["run_id"],
        "model_uri": training_result["model_uri"],
        "metrics": {
            "accuracy": training_result["accuracy"],
            "f1_score": training_result["f1_score"]
        },
        "metadata": {
            "description": "Demo classification model",
            "framework": "scikit-learn"
        }
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/models/register",
            headers=headers,
            json=registration_data
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"\n✅ Model registered with Hokusai!")
        print(f"   Model ID: {result.get('model_id', 'N/A')}")
        print(f"   Version: {result.get('version', 'N/A')}")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ Registration failed: {e}")
        print(f"   Response: {e.response.text}")
        return None


def main():
    """Main workflow."""
    print("🚀 Hokusai Model Registration Demo")
    print("==================================\n")
    
    # Step 1: Train and log model
    print("Step 1: Training model...")
    training_result = train_and_log_model()
    
    # Step 2: Register with Hokusai
    print("\nStep 2: Registering with Hokusai API...")
    registration = register_with_hokusai(training_result, TEST_PRIVATE_KEY)
    
    if registration:
        print("\n🎉 Success! Your model is now registered with Hokusai.")
        print(f"\nNext steps:")
        print(f"1. View your model in MLflow UI: {MLFLOW_TRACKING_URI}")
        print(f"2. Access model via API: GET {API_BASE_URL}/models/demo_classifier")
        print(f"3. Generate attestations for blockchain integration")
    else:
        print("\n⚠️  Registration failed. Please check:")
        print("1. API is accessible")
        print("2. Authentication is working")
        print("3. MLflow server is running")


if __name__ == "__main__":
    main()