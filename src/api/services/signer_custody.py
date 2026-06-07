"""Signer custody configuration and validation helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

import boto3


class SignerCustodyError(RuntimeError):
    """Raised when signer custody settings are unsafe for the target environment."""


class SignerCustodyMode(str, Enum):
    """Supported signer custody backends."""

    ENV = "env"
    KMS = "kms"


@dataclass(frozen=True)
class KMSSignerConfig:
    """Minimal KMS signer config surface for deployment wiring."""

    key_id: str
    region: str


def resolve_custody_mode(environment: str | None = None) -> SignerCustodyMode:
    """Resolve custody mode, defaulting to KMS only for production."""
    raw = os.getenv("SIGNER_CUSTODY_MODE")
    if raw:
        try:
            return SignerCustodyMode(raw.strip().lower())
        except ValueError as exc:
            raise SignerCustodyError(
                f"Invalid SIGNER_CUSTODY_MODE {raw!r}; expected 'env' or 'kms'"
            ) from exc

    env = (environment or os.getenv("ENVIRONMENT", "development")).strip().lower()
    if env == "production":
        return SignerCustodyMode.KMS
    return SignerCustodyMode.ENV


def validate_custody_for_env(mode: SignerCustodyMode, environment: str) -> None:
    """Reject env-backed signer custody in protected environments."""
    env = environment.strip().lower()
    if mode is SignerCustodyMode.ENV and env in {"production", "staging"}:
        raise SignerCustodyError(
            "SIGNER_CUSTODY_MODE=env is not allowed in staging or production; use kms"
        )


def kms_sign(payload: bytes, config: KMSSignerConfig) -> bytes:
    """Sign payload bytes via AWS KMS."""
    client: Any = boto3.client("kms", region_name=config.region)
    response = client.sign(
        KeyId=config.key_id,
        Message=payload,
        MessageType="RAW",
        SigningAlgorithm="ECDSA_SHA_256",
    )
    signature = response.get("Signature")
    if not isinstance(signature, (bytes, bytearray)):
        raise SignerCustodyError("KMS sign response did not include a binary Signature")
    return bytes(signature)
