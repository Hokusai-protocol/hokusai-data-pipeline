"""Security helpers for DeltaOne webhook signing and replay protection."""

from __future__ import annotations

import hashlib
import hmac
import uuid


def generate_nonce() -> str:
    """Generate a UUID4 nonce for replay protection."""
    return str(uuid.uuid4())


def sign_payload(payload: bytes, secret: str, timestamp: str, nonce: str) -> str:
    """Sign payload bytes using HMAC-SHA256 over timestamp.nonce.body."""
    signing_bytes = f"{timestamp}.{nonce}.".encode() + payload
    digest = hmac.new(secret.encode("utf-8"), signing_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(
    payload: bytes,
    secret: str,
    timestamp: str,
    nonce: str,
    provided_signature: str,
) -> bool:
    """Verify webhook signature using constant-time comparison."""
    expected_signature = sign_payload(payload, secret, timestamp, nonce)
    return hmac.compare_digest(expected_signature, provided_signature)
