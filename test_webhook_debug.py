#!/usr/bin/env python3
"""Debug script to test different webhook signature formats."""

import hashlib
import hmac
import json
import os
from datetime import datetime

import requests


def test_different_signatures():
    """Test different signature generation methods."""
    webhook_secret = "test_webhook_secret_for_development"

    # Create payload
    payload = {
        "event_type": "model_registered",
        "timestamp": datetime.utcnow().isoformat(),
        "token_id": "LSCOR",
        "model_name": "Sales lead scoring model",
        "model_version": "4",
        "mlflow_run_id": "test_run_id_123",
        "metric_name": "accuracy",
        "baseline_value": 0.933,
        "status": "REGISTERED",
        "tags": {"author": "GTM Backend Team", "version": "1.0.0", "dataset": "Kaggle B2B Sales"},
    }

    # Method 1: Compact JSON (no spaces)
    payload_compact = json.dumps(payload, separators=(",", ":"))
    sig_compact = hmac.new(
        webhook_secret.encode("utf-8"), payload_compact.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Method 2: Pretty JSON (with indent)
    payload_pretty = json.dumps(payload, indent=2)
    sig_pretty = hmac.new(
        webhook_secret.encode("utf-8"), payload_pretty.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Method 3: Standard JSON (default)
    payload_standard = json.dumps(payload)
    sig_standard = hmac.new(
        webhook_secret.encode("utf-8"), payload_standard.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Method 4: Without sha256= prefix
    sig_raw = hmac.new(
        webhook_secret.encode("utf-8"), payload_compact.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    print("Testing different signature formats:")
    print(f"1. Compact JSON signature: sha256={sig_compact[:20]}...")
    print(f"2. Pretty JSON signature:  sha256={sig_pretty[:20]}...")
    print(f"3. Standard JSON signature: sha256={sig_standard[:20]}...")
    print(f"4. Raw signature (no prefix): {sig_raw[:20]}...")

    # Try each format
    webhook_url = "https://hokus.ai/api/mlflow/registered"

    formats = [
        ("Compact JSON with sha256= prefix", payload_compact, f"sha256={sig_compact}"),
        ("Compact JSON without prefix", payload_compact, sig_compact),
        ("Standard JSON with sha256= prefix", payload_standard, f"sha256={sig_standard}"),
        ("Standard JSON without prefix", payload_standard, sig_standard),
    ]

    for description, payload_bytes, signature in formats:
        print(f"\n\nTrying: {description}")
        print(f"Signature: {signature[:30]}...")

        headers = {
            "Content-Type": "application/json",
            "x-mlflow-signature": signature,
        }

        try:
            response = requests.post(
                webhook_url,
                data=payload_bytes.encode("utf-8")
                if isinstance(payload_bytes, str)
                else payload_bytes,
                headers=headers,
                timeout=10,
            )

            print(f"Status: {response.status_code}")
            if response.text:
                print(f"Response: {response.text}")

            if response.status_code == 200:
                print("✅ SUCCESS! This signature format works!")
                return True

        except Exception as e:
            print(f"Error: {e}")

    return False


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

    test_different_signatures()
