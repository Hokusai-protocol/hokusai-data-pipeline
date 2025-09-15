#!/usr/bin/env python3
"""Simple webhook test with minimal payload."""

import hashlib
import hmac
import json

import requests

# Test with the exact same secret the website should have
webhook_secret = "test_webhook_secret_for_development"
webhook_url = "https://hokus.ai/api/mlflow/registered"

# Simple test payload
payload = {"test": "hello"}

# Generate signature using the exact same method
payload_string = json.dumps(payload, separators=(",", ":"))
signature = hmac.new(
    webhook_secret.encode("utf-8"), payload_string.encode("utf-8"), hashlib.sha256
).hexdigest()

print(f"Secret: {webhook_secret}")
print(f"Payload: {payload_string}")
print(f"Signature: {signature}")

# Try with and without sha256= prefix
for sig_format in [f"sha256={signature}", signature]:
    print(f"\nTrying signature format: {sig_format[:40]}...")

    headers = {
        "Content-Type": "application/json",
        "x-mlflow-signature": sig_format,
    }

    response = requests.post(webhook_url, data=payload_string, headers=headers, timeout=10)

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

    if response.status_code == 200:
        print("✅ This format works!")
        break
