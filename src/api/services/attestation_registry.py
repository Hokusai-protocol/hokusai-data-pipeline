"""Redis-backed registry for consumed attestations and nonces."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from redis import Redis

DEFAULT_USED_ATTESTATION_TTL_SECONDS = 90 * 24 * 60 * 60


class AttestationAlreadyConsumedError(RuntimeError):
    """Raised when a consumed attestation hash is consumed again."""


class AttestationNonceAlreadyUsedError(RuntimeError):
    """Raised when an attestation nonce is reused."""


@dataclass(frozen=True, slots=True)
class ConsumedAttestationMetadata:
    """Normalized consumed-attestation metadata."""

    mint_audit_ref: str
    model_id: str
    consumed_at: str
    decision_summary: dict[str, Any]
    nonce: str | None = None

    def to_dict(self: ConsumedAttestationMetadata) -> dict[str, Any]:
        payload = {
            "mint_audit_ref": self.mint_audit_ref,
            "model_id": self.model_id,
            "consumed_at": self.consumed_at,
            "decision_summary": self.decision_summary,
        }
        if self.nonce:
            payload["nonce"] = self.nonce
        return payload


class AttestationRegistry:
    """Tracks attestation hash consumption and nonce uniqueness in Redis."""

    def __init__(
        self: AttestationRegistry,
        redis_client: Redis,
        ttl_seconds: int | None = None,
        key_prefix: str = "attestation",
    ) -> None:
        self._redis = redis_client
        configured_ttl = ttl_seconds or int(
            os.getenv("ATTESTATION_REGISTRY_TTL_SECONDS", str(DEFAULT_USED_ATTESTATION_TTL_SECONDS))
        )
        self._ttl_seconds = max(1, configured_ttl)
        self._key_prefix = key_prefix

    def is_consumed(self: AttestationRegistry, attestation_hash: str) -> bool:
        """Return whether attestation hash has already been consumed."""
        return bool(self._redis.exists(self._used_key(attestation_hash)))

    def consume(
        self: AttestationRegistry,
        attestation_hash: str,
        metadata: dict[str, Any],
        nonce: str | None = None,
    ) -> None:
        """Consume an attestation hash atomically; fail if hash or nonce already used."""
        now = datetime.now(timezone.utc).isoformat()
        normalized = ConsumedAttestationMetadata(
            mint_audit_ref=str(metadata.get("mint_audit_ref", "")),
            model_id=str(metadata.get("model_id", "")),
            consumed_at=str(metadata.get("consumed_at", now)),
            decision_summary=dict(metadata.get("decision_summary", {})),
            nonce=nonce,
        )
        payload = json.dumps(normalized.to_dict(), sort_keys=True)

        nonce_key = self._nonce_key(nonce) if nonce else None
        nonce_reserved = False
        if nonce_key:
            nonce_reserved = bool(
                self._redis.set(
                    nonce_key,
                    attestation_hash,
                    ex=self._ttl_seconds,
                    nx=True,
                )
            )
            if not nonce_reserved:
                raise AttestationNonceAlreadyUsedError(f"Attestation nonce already used: {nonce}")

        consumed = bool(
            self._redis.set(
                self._used_key(attestation_hash),
                payload,
                ex=self._ttl_seconds,
                nx=True,
            )
        )
        if consumed:
            return

        if nonce_key and nonce_reserved:
            self._redis.delete(nonce_key)
        raise AttestationAlreadyConsumedError(
            f"Attestation hash already consumed: {attestation_hash}"
        )

    def _used_key(self: AttestationRegistry, attestation_hash: str) -> str:
        return f"{self._key_prefix}:used:{attestation_hash}"

    def _nonce_key(self: AttestationRegistry, nonce: str) -> str:
        return f"{self._key_prefix}:nonce:{nonce}"
