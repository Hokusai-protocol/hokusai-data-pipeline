"""Unit tests for used-attestation registry replay protection."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import fakeredis
import pytest

from src.api.services.attestation_registry import (
    AttestationAlreadyConsumedError,
    AttestationNonceAlreadyUsedError,
    AttestationRegistry,
)


def test_first_consume_succeeds_and_marks_consumed() -> None:
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    registry = AttestationRegistry(redis_client=redis_client, ttl_seconds=60)

    registry.consume(
        "a" * 64,
        metadata={
            "mint_audit_ref": "audit-1",
            "model_id": "model-a",
            "decision_summary": {"accepted": True},
        },
        nonce="nonce-1",
    )

    assert registry.is_consumed("a" * 64) is True


def test_second_consume_raises() -> None:
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    registry = AttestationRegistry(redis_client=redis_client, ttl_seconds=60)

    registry.consume(
        "b" * 64,
        metadata={
            "mint_audit_ref": "audit-1",
            "model_id": "model-a",
            "decision_summary": {"accepted": True},
        },
        nonce="nonce-2",
    )
    with pytest.raises(AttestationAlreadyConsumedError):
        registry.consume(
            "b" * 64,
            metadata={
                "mint_audit_ref": "audit-2",
                "model_id": "model-a",
                "decision_summary": {"accepted": True},
            },
            nonce="nonce-3",
        )


def test_nonce_reuse_raises() -> None:
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    registry = AttestationRegistry(redis_client=redis_client, ttl_seconds=60)

    registry.consume(
        "c" * 64,
        metadata={
            "mint_audit_ref": "audit-1",
            "model_id": "model-a",
            "decision_summary": {"accepted": True},
        },
        nonce="nonce-x",
    )
    with pytest.raises(AttestationNonceAlreadyUsedError):
        registry.consume(
            "d" * 64,
            metadata={
                "mint_audit_ref": "audit-2",
                "model_id": "model-a",
                "decision_summary": {"accepted": True},
            },
            nonce="nonce-x",
        )


def test_ttl_expiry_allows_reuse_after_expiration() -> None:
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    registry = AttestationRegistry(redis_client=redis_client, ttl_seconds=1)
    attestation_hash = "e" * 64

    registry.consume(
        attestation_hash,
        metadata={
            "mint_audit_ref": "audit-1",
            "model_id": "model-a",
            "decision_summary": {"accepted": True},
        },
    )
    assert registry.is_consumed(attestation_hash) is True

    time.sleep(1.1)
    assert registry.is_consumed(attestation_hash) is False

    registry.consume(
        attestation_hash,
        metadata={
            "mint_audit_ref": "audit-2",
            "model_id": "model-a",
            "decision_summary": {"accepted": True},
        },
    )


def test_concurrent_consume_allows_only_one_success() -> None:
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    registry = AttestationRegistry(redis_client=redis_client, ttl_seconds=60)
    attestation_hash = "f" * 64

    def _attempt() -> str:
        try:
            registry.consume(
                attestation_hash,
                metadata={
                    "mint_audit_ref": "audit-concurrent",
                    "model_id": "model-a",
                    "decision_summary": {"accepted": True},
                },
            )
            return "ok"
        except AttestationAlreadyConsumedError:
            return "already"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: _attempt(), range(8)))

    assert results.count("ok") == 1
    assert results.count("already") == 7
