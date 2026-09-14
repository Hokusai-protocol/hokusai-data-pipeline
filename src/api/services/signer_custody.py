"""Signer custody configuration and the attester signing primitives.

The DeltaVerifier requires EIP-712 attester signatures over a keccak256 digest, signed with
secp256k1 (Ethereum's ``r||s||v`` form). Two custody backends are supported:

* ``env`` -- a local secp256k1 private key (dev / testnet / canary only; rejected in
  staging/production by :func:`validate_custody_for_env`).
* ``kms`` -- an AWS KMS ``ECC_SECG_P256K1`` key. KMS only offers the ``ECDSA_SHA_256``
  signing algorithm for secp256k1, so we pass the already-hashed digest with
  ``MessageType=DIGEST`` (KMS does not re-hash) and convert the DER signature it returns into
  Ethereum's low-s ``r||s||v`` form, recovering ``v`` against the key's own address.

This replaces the previous scaffold which signed with ``MessageType=RAW`` (which made KMS apply
SHA-256 to the input -- wrong for an already-keccak256 Ethereum digest) and returned the raw DER
bytes (unusable on-chain).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

import boto3
from cryptography.hazmat.primitives.serialization import load_der_public_key
from eth_keys import keys
from eth_utils import keccak

# secp256k1 group order; used to enforce EIP-2 low-s signatures.
_SECP256K1_N = int("0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141", 16)
_SECP256K1_HALF_N = _SECP256K1_N // 2


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


def _encode_eth_signature(*, r: int, s: int, recovery_id: int) -> str:
    """Encode (r, s, recovery_id) as a 65-byte 0x ``r||s||v`` signature in low-s form.

    Normalizes ``s`` to the lower half of the curve order (EIP-2); flipping ``s`` flips the
    recovery parity, so ``recovery_id`` is flipped to match. ``v`` is emitted as 27/28.
    """
    if recovery_id not in (0, 1):
        raise SignerCustodyError(f"recovery_id must be 0 or 1, got {recovery_id}")
    if s > _SECP256K1_HALF_N:
        s = _SECP256K1_N - s
        recovery_id ^= 1
    v = recovery_id + 27
    return "0x" + r.to_bytes(32, "big").hex() + s.to_bytes(32, "big").hex() + bytes([v]).hex()


def _normalize_private_key(private_key: str) -> bytes:
    body = private_key.strip().removeprefix("0x")
    try:
        raw = bytes.fromhex(body)
    except ValueError as exc:
        raise SignerCustodyError("attester private key must be valid hexadecimal") from exc
    if len(raw) != 32:
        raise SignerCustodyError(f"attester private key must be 32 bytes, got {len(raw)}")
    return raw


def sign_digest_with_private_key(digest: bytes, private_key: str) -> str:
    """Sign a 32-byte keccak digest with a local secp256k1 key (env custody)."""
    if len(digest) != 32:
        raise SignerCustodyError(f"digest must be 32 bytes, got {len(digest)}")
    signing_key = keys.PrivateKey(_normalize_private_key(private_key))
    signature = signing_key.sign_msg_hash(digest)
    return _encode_eth_signature(r=signature.r, s=signature.s, recovery_id=signature.v)


def address_for_private_key(private_key: str) -> str:
    """Return the lowercase 0x address controlled by a local secp256k1 key."""
    signing_key = keys.PrivateKey(_normalize_private_key(private_key))
    return "0x" + signing_key.public_key.to_canonical_address().hex()


def kms_public_key_to_address(spki_der: bytes) -> str:
    """Derive the lowercase 0x Ethereum address from a DER SubjectPublicKeyInfo."""
    public_key = load_der_public_key(spki_der)
    numbers = public_key.public_numbers()
    uncompressed = numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    return "0x" + keccak(uncompressed)[-20:].hex()


def derive_kms_attester_address(config: KMSSignerConfig) -> str:
    """Fetch the KMS key's public key and derive its Ethereum address."""
    client: Any = boto3.client("kms", region_name=config.region)
    response = client.get_public_key(KeyId=config.key_id)
    spki_der = response.get("PublicKey")
    if not isinstance(spki_der, (bytes, bytearray)):
        raise SignerCustodyError("KMS get_public_key response did not include a binary PublicKey")
    return kms_public_key_to_address(bytes(spki_der))


def _der_to_rs(der_signature: bytes) -> tuple[int, int]:
    from cryptography.hazmat.primitives.asymmetric.utils import (  # noqa: PLC0415
        decode_dss_signature,
    )

    r, s = decode_dss_signature(der_signature)
    return int(r), int(s)


def _recover_id_for_address(*, digest: bytes, r: int, s: int, expected_address: str) -> int:
    target = expected_address.strip().lower().removeprefix("0x")
    for recovery_id in (0, 1):
        try:
            candidate = keys.Signature(vrs=(recovery_id, r, s))
            recovered = candidate.recover_public_key_from_msg_hash(digest)
        except Exception:  # noqa: BLE001, S112  # invalid recovery id -> try the other parity
            continue
        if recovered.to_canonical_address().hex() == target:
            return recovery_id
    raise SignerCustodyError("KMS signature does not recover the expected attester address")


def kms_sign_digest(
    digest: bytes,
    config: KMSSignerConfig,
    *,
    expected_address: str | None = None,
) -> str:
    """Sign a 32-byte keccak digest via AWS KMS and return Ethereum ``r||s||v`` form.

    KMS signs the digest directly (``MessageType=DIGEST``); the DER signature it returns is
    converted to low-s ``r||s||v``, with ``v`` recovered against ``expected_address`` (defaults
    to the KMS key's own derived address).
    """
    if len(digest) != 32:
        raise SignerCustodyError(f"digest must be 32 bytes, got {len(digest)}")
    target_address = expected_address or derive_kms_attester_address(config)

    client: Any = boto3.client("kms", region_name=config.region)
    response = client.sign(
        KeyId=config.key_id,
        Message=digest,
        MessageType="DIGEST",
        SigningAlgorithm="ECDSA_SHA_256",
    )
    der_signature = response.get("Signature")
    if not isinstance(der_signature, (bytes, bytearray)):
        raise SignerCustodyError("KMS sign response did not include a binary Signature")

    r, s = _der_to_rs(bytes(der_signature))
    # Normalize low-s before recovering v so the recovery parity matches the emitted signature.
    low_s = _SECP256K1_N - s if s > _SECP256K1_HALF_N else s
    recovery_id = _recover_id_for_address(
        digest=digest, r=r, s=low_s, expected_address=target_address
    )
    return _encode_eth_signature(r=r, s=low_s, recovery_id=recovery_id)


def sign_attestation_digest(
    digest: bytes,
    *,
    mode: SignerCustodyMode,
    private_key: str | None = None,
    kms_config: KMSSignerConfig | None = None,
    expected_address: str | None = None,
) -> str:
    """Sign a keccak digest with the configured custody backend, returning ``r||s||v`` hex."""
    if mode is SignerCustodyMode.ENV:
        if not private_key:
            raise SignerCustodyError("env custody requires an attester private key")
        return sign_digest_with_private_key(digest, private_key)
    if mode is SignerCustodyMode.KMS:
        if kms_config is None:
            raise SignerCustodyError("kms custody requires a KMSSignerConfig")
        return kms_sign_digest(digest, kms_config, expected_address=expected_address)
    raise SignerCustodyError(f"unsupported signer custody mode: {mode}")
