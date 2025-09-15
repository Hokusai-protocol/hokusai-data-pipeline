#!/usr/bin/env python3
"""Test different signature methods that the website might be using."""

import base64
import hashlib
import hmac
import json

import requests

webhook_secret = "test_webhook_secret_for_development"
webhook_url = "https://hokus.ai/api/mlflow/registered"

# Simple test payload
payload = {"test": "hello"}
payload_string = json.dumps(payload, separators=(",", ":"))

print(f"Testing with payload: {payload_string}")
print(f"Secret: {webhook_secret}\n")

# Method 1: HMAC-SHA256 hex digest (what we're using)
sig_hex = hmac.new(
    webhook_secret.encode("utf-8"), payload_string.encode("utf-8"), hashlib.sha256
).hexdigest()

# Method 2: HMAC-SHA256 base64
sig_bytes = hmac.new(
    webhook_secret.encode("utf-8"), payload_string.encode("utf-8"), hashlib.sha256
).digest()
sig_base64 = base64.b64encode(sig_bytes).decode("utf-8")

# Method 3: SHA256 (no HMAC)
sig_sha256 = hashlib.sha256(payload_string.encode("utf-8")).hexdigest()

# Method 4: HMAC with different key format (maybe the site adds something)
sig_with_prefix = hmac.new(
    f"secret_{webhook_secret}".encode(), payload_string.encode("utf-8"), hashlib.sha256
).hexdigest()

# Method 5: Maybe the entire request body needs to be signed
full_body = json.dumps(payload)  # Without compact formatting
sig_full = hmac.new(
    webhook_secret.encode("utf-8"), full_body.encode("utf-8"), hashlib.sha256
).hexdigest()

methods = [
    ("HMAC-SHA256 hex with sha256= prefix", payload_string, f"sha256={sig_hex}"),
    ("HMAC-SHA256 hex without prefix", payload_string, sig_hex),
    ("HMAC-SHA256 base64", payload_string, sig_base64),
    ("SHA256 (no HMAC)", payload_string, sig_sha256),
    ("HMAC with secret_ prefix", payload_string, sig_with_prefix),
    ("HMAC with non-compact JSON", full_body, sig_full),
]

for description, body, signature in methods:
    print(f"\nTrying: {description}")
    print(f"Signature: {signature[:40]}...")

    headers = {
        "Content-Type": "application/json",
        "x-mlflow-signature": signature,
    }

    try:
        response = requests.post(webhook_url, data=body, headers=headers, timeout=10)

        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            print("✅ SUCCESS! This method works!")
            print(f"Working signature method: {description}")
            print(f"Body format: {body}")
            print(f"Signature: {signature}")
            break

    except Exception as e:
        print(f"Error: {e}")
