"""Unit tests for signer custody validation and the attester signing primitives."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from eth_keys import keys
from eth_utils import keccak

from src.api.services import signer_custody
from src.api.services.signer_custody import (
    KMSSignerConfig,
    SignerCustodyError,
    SignerCustodyMode,
    address_for_private_key,
    derive_kms_attester_address,
    kms_public_key_to_address,
    kms_sign_digest,
    resolve_custody_mode,
    sign_attestation_digest,
    sign_digest_with_private_key,
    validate_custody_for_env,
)

# Deterministic (RFC 6979) test key; never used outside tests.
_TEST_PRIVATE_KEY = "0x" + "ab" * 32
_DIGEST = keccak(text="hok-2245 attester digest")
_SECP256K1_HALF_N = (
    int("0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141", 16) // 2
)


def _spki_der_for(private_key: str) -> bytes:
    pub = keys.PrivateKey(bytes.fromhex(private_key.removeprefix("0x"))).public_key.to_bytes()
    numbers = ec.EllipticCurvePublicNumbers(
        int.from_bytes(pub[:32], "big"), int.from_bytes(pub[32:], "big"), ec.SECP256K1()
    )
    return numbers.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def test_env_custody_rejected_on_production() -> None:
    with pytest.raises(SignerCustodyError):
        validate_custody_for_env(SignerCustodyMode.ENV, "production")


def test_env_custody_allowed_on_development() -> None:
    validate_custody_for_env(SignerCustodyMode.ENV, "development")


def test_kms_custody_allowed_everywhere() -> None:
    validate_custody_for_env(SignerCustodyMode.KMS, "development")
    validate_custody_for_env(SignerCustodyMode.KMS, "staging")
    validate_custody_for_env(SignerCustodyMode.KMS, "production")


def test_resolve_custody_mode_defaults_to_kms_on_production(monkeypatch) -> None:
    monkeypatch.delenv("SIGNER_CUSTODY_MODE", raising=False)

    assert resolve_custody_mode("production") is SignerCustodyMode.KMS


def _recover(signature_hex: str, digest: bytes) -> str:
    raw = bytes.fromhex(signature_hex.removeprefix("0x"))
    r = int.from_bytes(raw[:32], "big")
    s = int.from_bytes(raw[32:64], "big")
    recovery_id = raw[64] - 27
    pub = keys.Signature(vrs=(recovery_id, r, s)).recover_public_key_from_msg_hash(digest)
    return "0x" + pub.to_canonical_address().hex()


def test_local_signer_produces_low_s_recoverable_signature() -> None:
    signature = sign_digest_with_private_key(_DIGEST, _TEST_PRIVATE_KEY)

    raw = bytes.fromhex(signature.removeprefix("0x"))
    assert len(raw) == 65
    assert raw[64] in (27, 28)
    assert int.from_bytes(raw[32:64], "big") <= _SECP256K1_HALF_N  # EIP-2 low-s
    assert _recover(signature, _DIGEST) == address_for_private_key(_TEST_PRIVATE_KEY)


def test_local_signer_rejects_bad_key_and_digest() -> None:
    with pytest.raises(SignerCustodyError):
        sign_digest_with_private_key(_DIGEST, "0x1234")  # not 32 bytes
    with pytest.raises(SignerCustodyError):
        sign_digest_with_private_key(b"\x00" * 31, _TEST_PRIVATE_KEY)  # not 32-byte digest


def test_kms_address_derivation_matches_local_address() -> None:
    derived = kms_public_key_to_address(_spki_der_for(_TEST_PRIVATE_KEY))
    assert derived == address_for_private_key(_TEST_PRIVATE_KEY)


def _mock_kms_client(private_key: str, digest: bytes) -> Mock:
    """A KMS client whose sign() returns a DER signature over `digest` from `private_key`."""
    signature = keys.PrivateKey(bytes.fromhex(private_key.removeprefix("0x"))).sign_msg_hash(digest)
    der = encode_dss_signature(signature.r, signature.s)
    client = Mock()
    client.sign.return_value = {"Signature": der}
    client.get_public_key.return_value = {"PublicKey": _spki_der_for(private_key)}
    return client


def test_kms_sign_digest_matches_local_signature(monkeypatch) -> None:
    client = _mock_kms_client(_TEST_PRIVATE_KEY, _DIGEST)
    monkeypatch.setattr(signer_custody.boto3, "client", lambda *a, **k: client)
    config = KMSSignerConfig(key_id="alias/attester", region="us-east-1")

    signature = kms_sign_digest(_DIGEST, config)

    # Same key + digest (RFC 6979) -> identical Ethereum signature as the local signer.
    assert signature == sign_digest_with_private_key(_DIGEST, _TEST_PRIVATE_KEY)
    assert _recover(signature, _DIGEST) == address_for_private_key(_TEST_PRIVATE_KEY)
    # Signs the digest directly (no re-hash); never MessageType=RAW.
    assert client.sign.call_args.kwargs["MessageType"] == "DIGEST"
    assert derive_kms_attester_address(config) == address_for_private_key(_TEST_PRIVATE_KEY)


def test_kms_sign_digest_rejects_wrong_expected_address(monkeypatch) -> None:
    client = _mock_kms_client(_TEST_PRIVATE_KEY, _DIGEST)
    monkeypatch.setattr(signer_custody.boto3, "client", lambda *a, **k: client)
    config = KMSSignerConfig(key_id="alias/attester", region="us-east-1")

    with pytest.raises(SignerCustodyError, match="expected attester address"):
        kms_sign_digest(_DIGEST, config, expected_address="0x" + "11" * 20)


def test_sign_attestation_digest_dispatches_by_mode(monkeypatch) -> None:
    env_sig = sign_attestation_digest(
        _DIGEST, mode=SignerCustodyMode.ENV, private_key=_TEST_PRIVATE_KEY
    )
    assert env_sig == sign_digest_with_private_key(_DIGEST, _TEST_PRIVATE_KEY)

    with pytest.raises(SignerCustodyError):
        sign_attestation_digest(_DIGEST, mode=SignerCustodyMode.ENV)  # missing key

    client = _mock_kms_client(_TEST_PRIVATE_KEY, _DIGEST)
    monkeypatch.setattr(signer_custody.boto3, "client", lambda *a, **k: client)
    kms_sig = sign_attestation_digest(
        _DIGEST,
        mode=SignerCustodyMode.KMS,
        kms_config=KMSSignerConfig(key_id="alias/attester", region="us-east-1"),
    )
    assert kms_sig == env_sig
