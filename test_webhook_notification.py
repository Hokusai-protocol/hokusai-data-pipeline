#!/usr/bin/env python3
"""Test script to verify webhook notification for model registration.

This script tests the webhook that notifies the Hokusai website
to update token status from DRAFT to REGISTERED.
"""

import hashlib
import hmac
import json
import os
from datetime import datetime

import requests


def test_webhook_notification():
    """Test sending a webhook notification to the Hokusai website."""
    # Load environment variables
    webhook_url = os.getenv("WEBHOOK_URL", "https://hokus.ai/api/mlflow/registered")
    webhook_secret = os.getenv("WEBHOOK_SECRET", "test_webhook_secret_for_development")

    print(f"Testing webhook notification to: {webhook_url}")
    print(f"Using secret: {webhook_secret[:10]}...")

    # Create a test payload similar to what would be sent after model registration
    payload = {
        "model": {
            "id": "LSCOR",  # Website expects 'id' field
            "name": "Sales lead scoring model",
            "version": "4",
            "mlflow_run_id": "test_run_id_123",
            "metric_name": "accuracy",
            "baseline_value": 0.933,
            "token_id": "LSCOR",
            "status": "registered",  # Must be lowercase
            "tags": {
                "author": "GTM Backend Team",
                "version": "1.0.0",
                "dataset": "Kaggle B2B Sales",
            },
        },
        "source": "mlflow",
        "event_type": "model_registered",
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Serialize payload
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_bytes = payload_json.encode("utf-8")

    # Generate HMAC signature
    signature = hmac.new(webhook_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "x-mlflow-signature": f"sha256={signature}",
        "X-Hokusai-Event": "model_registered",
    }

    print("\nPayload to send:")
    print(json.dumps(payload, indent=2))

    print("\nHeaders:")
    for key, value in headers.items():
        if key == "x-mlflow-signature":
            print(f"  {key}: sha256={signature[:10]}...")
        else:
            print(f"  {key}: {value}")

    # Send the webhook
    try:
        print("\nSending webhook...")
        response = requests.post(webhook_url, data=payload_bytes, headers=headers, timeout=10)

        print(f"\nResponse Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        if response.text:
            print(f"Response Body: {response.text}")

        if response.status_code >= 200 and response.status_code < 300:
            print("\n✅ SUCCESS: Webhook notification sent successfully!")
            print("The Hokusai website should now update the token status to REGISTERED.")
        else:
            print(f"\n❌ FAILED: Webhook returned status code {response.status_code}")
            print("The token may still show as DRAFT on the website.")

    except requests.exceptions.Timeout:
        print("\n❌ ERROR: Request timed out after 10 seconds")
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ ERROR: Could not connect to {webhook_url}")
        print(f"Details: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: Unexpected error occurred: {e}")


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
                    key, value = line.split("=", 1)
                    os.environ[key] = value

    test_webhook_notification()
