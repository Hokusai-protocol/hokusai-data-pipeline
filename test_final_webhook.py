#!/usr/bin/env python3
"""Final test to verify the complete webhook integration works.
This simulates what happens when register_tokenized_model() is called.
"""

import hashlib
import hmac
import json
import os
from datetime import datetime

import requests


def test_model_registration_webhook():
    """Test the complete model registration webhook flow."""
    # Load environment variables
    webhook_url = os.getenv("WEBHOOK_URL", "https://hokus.ai/api/mlflow/registered")
    webhook_secret = os.getenv("WEBHOOK_SECRET", "test_webhook_secret_for_development")

    print("=" * 60)
    print("HOKUSAI MODEL REGISTRATION WEBHOOK TEST")
    print("=" * 60)
    print(f"\nWebhook URL: {webhook_url}")
    print(f"Using secret: {webhook_secret[:20]}...")

    # Simulate a real model registration
    model_info = {
        "token_id": "LSCOR",
        "model_name": "Sales lead scoring model",
        "model_version": "5",  # Next version after 4
        "mlflow_run_id": "actual_run_abc123",
        "metric_name": "accuracy",
        "baseline_value": 0.933,
        "tags": {
            "author": "GTM Backend Team",
            "version": "1.0.1",
            "dataset": "Kaggle B2B Sales",
            "improved": "true",
        },
    }

    # Create the exact payload format the website expects
    payload = {
        "model": {
            "id": model_info["token_id"],
            "name": model_info["model_name"],
            "version": model_info["model_version"],
            "mlflow_run_id": model_info["mlflow_run_id"],
            "metric_name": model_info["metric_name"],
            "baseline_value": model_info["baseline_value"],
            "token_id": model_info["token_id"],
            "status": "registered",  # lowercase
            "tags": model_info["tags"],
        },
        "source": "mlflow",
        "event_type": "model_registered",
        "timestamp": datetime.utcnow().isoformat(),
    }

    print("\n📦 PAYLOAD TO SEND:")
    print("-" * 40)
    print(json.dumps(payload, indent=2))

    # Generate HMAC signature
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_bytes = payload_json.encode("utf-8")

    signature = hmac.new(webhook_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "x-mlflow-signature": f"sha256={signature}",
        "X-Hokusai-Event": "model_registered",
    }

    print("\n🔐 SECURITY:")
    print("-" * 40)
    print(f"Signature: sha256={signature[:20]}...")
    print(f"Headers: {list(headers.keys())}")

    # Send the webhook
    print("\n📤 SENDING WEBHOOK...")
    print("-" * 40)

    try:
        response = requests.post(webhook_url, data=payload_bytes, headers=headers, timeout=10)

        print(f"Response Status: {response.status_code}")

        if response.text:
            try:
                response_json = response.json()
                print(f"Response Body: {json.dumps(response_json, indent=2)}")
            except:
                print(f"Response Body: {response.text}")

        print("\n" + "=" * 60)
        if response.status_code >= 200 and response.status_code < 300:
            print("✅ SUCCESS! Webhook delivered successfully!")
            print("\n📊 WHAT THIS MEANS:")
            print("-" * 40)
            print(f"• Token '{model_info['token_id']}' status updated to REGISTERED")
            print(f"• Model version {model_info['model_version']} is now active")
            print("• Check https://hokus.ai/explore-models/ to see the update")
            print("\n🎉 The integration is working correctly!")
        else:
            print(f"❌ FAILED: Webhook returned status {response.status_code}")
            print("\n⚠️  The token may still show as DRAFT on the website.")

    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out")
    except requests.exceptions.ConnectionError as e:
        print(f"❌ ERROR: Could not connect to {webhook_url}")
        print(f"Details: {e}")
    except Exception as e:
        print(f"❌ ERROR: {e}")

    print("=" * 60)


if __name__ == "__main__":
    # Load .env file if it exists
    from pathlib import Path

    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        print(f"Loading environment from {env_file}")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key] = value

    test_model_registration_webhook()
