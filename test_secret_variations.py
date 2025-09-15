#!/usr/bin/env python3
"""Test with different secret variations in case there's a mismatch."""

import hashlib
import hmac
import json

import requests

webhook_url = "https://hokus.ai/api/mlflow/registered"

# Simple test payload
payload = {"test": "hello"}
payload_string = json.dumps(payload, separators=(",", ":"))

# Try different secret variations
secrets = [
    "test_webhook_secret_for_development",  # What we have
    "test_webhook_secret_for_development\n",  # With newline
    "test_webhook_secret_for_development ",  # With space
    " test_webhook_secret_for_development",  # Leading space
    "TEST_WEBHOOK_SECRET_FOR_DEVELOPMENT",  # Uppercase
    "",  # Empty
    "webhook_secret",  # Simple version
    "development",  # Just the env
]

print(f"Testing with payload: {payload_string}\n")

for secret in secrets:
    sig = hmac.new(
        secret.encode("utf-8"), payload_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    print(f"\nTrying secret: '{secret}' (length: {len(secret)})")
    print(f"Signature: {sig[:30]}...")

    headers = {
        "Content-Type": "application/json",
        "x-mlflow-signature": f"sha256={sig}",
    }

    try:
        response = requests.post(webhook_url, data=payload_string, headers=headers, timeout=10)

        if response.status_code == 200:
            print(f"✅ SUCCESS with secret: '{secret}'")
            break
        elif response.status_code != 401:
            print(f"Status: {response.status_code}, Response: {response.text}")

    except Exception as e:
        print(f"Error: {e}")
else:
    print("\n❌ None of the secret variations worked")
    print("\nThe website might be configured with a different webhook secret.")
    print("Please verify the WEBHOOK_SECRET environment variable on the website.")
