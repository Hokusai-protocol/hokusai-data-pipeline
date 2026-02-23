"""DeltaOne mint orchestration with attestation replay protection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.api.schemas.token_mint import TokenMintResult
from src.api.services.attestation_registry import (
    AttestationAlreadyConsumedError,
    AttestationRegistry,
)
from src.api.services.score_history_audit import ScoreHistoryAudit
from src.api.services.token_mint_hook import TokenMintHook
from src.evaluation.deltaone_evaluator import DeltaOneDecision


class AttestationSpecSupersededError(RuntimeError):
    """Raised when attestation references a benchmark spec that is no longer active."""


class BenchmarkSpecResolverProtocol(Protocol):
    """Resolver contract for active benchmark specs."""

    def get_active_spec_for_model(
        self: BenchmarkSpecResolverProtocol, model_id: str
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class MintRequestContext:
    """Input payload required for one DeltaOne mint attempt."""

    token_id: str
    attestation_hash: str
    attestation_payload: dict[str, Any]


class DeltaOneMintOrchestrator:
    """Coordinates minting and used-attestation writes."""

    def __init__(
        self: DeltaOneMintOrchestrator,
        mint_hook: TokenMintHook,
        attestation_registry: AttestationRegistry,
        benchmark_spec_resolver: BenchmarkSpecResolverProtocol | None = None,
        score_history_audit: ScoreHistoryAudit | None = None,
    ) -> None:
        self._mint_hook = mint_hook
        self._attestation_registry = attestation_registry
        self._benchmark_spec_resolver = benchmark_spec_resolver
        self._score_history_audit = score_history_audit

    def mint_for_decision(
        self: DeltaOneMintOrchestrator,
        *,
        decision: DeltaOneDecision,
        request: MintRequestContext,
    ) -> TokenMintResult | None:
        """Mint tokens for accepted decisions using attestation replay protection."""
        if not decision.accepted:
            return None

        self._ensure_spec_not_superseded(
            model_id=decision.model_id,
            attestation_payload=request.attestation_payload,
        )

        if self._attestation_registry.is_consumed(request.attestation_hash):
            raise AttestationAlreadyConsumedError(
                f"Attestation hash already consumed: {request.attestation_hash}"
            )

        mint_result = self._mint_hook.mint(
            model_id=decision.model_id,
            token_id=request.token_id,
            delta_value=decision.delta_percentage_points,
            idempotency_key=f"attestation:{request.attestation_hash}",
            metadata={
                "attestation_hash": request.attestation_hash,
                "deltaone_reason": decision.reason,
                "baseline_run_id": decision.baseline_run_id,
                "run_id": decision.run_id,
            },
        )

        if mint_result.status in {"success", "dry_run", "skipped"}:
            self._attestation_registry.consume(
                request.attestation_hash,
                metadata={
                    "mint_audit_ref": mint_result.audit_ref,
                    "model_id": decision.model_id,
                    "decision_summary": {
                        "accepted": decision.accepted,
                        "reason": decision.reason,
                        "delta_percentage_points": decision.delta_percentage_points,
                        "baseline_run_id": decision.baseline_run_id,
                        "run_id": decision.run_id,
                    },
                },
                nonce=request.attestation_payload.get("attestation_nonce"),
            )
            if self._score_history_audit is not None:
                self._score_history_audit.record_transition(
                    model_id=decision.model_id,
                    attestation_hash=request.attestation_hash,
                    baseline_run_id=decision.baseline_run_id,
                    run_id=decision.run_id,
                    delta_percentage_points=decision.delta_percentage_points,
                    decision_reason=decision.reason,
                )

        return mint_result

    def _ensure_spec_not_superseded(
        self: DeltaOneMintOrchestrator,
        *,
        model_id: str,
        attestation_payload: dict[str, Any],
    ) -> None:
        if self._benchmark_spec_resolver is None:
            return

        active_spec = self._benchmark_spec_resolver.get_active_spec_for_model(model_id)
        if active_spec is None:
            return

        attested_spec_id = attestation_payload.get("benchmark_spec_id")
        if attested_spec_id and str(attested_spec_id) != str(active_spec.get("spec_id")):
            raise AttestationSpecSupersededError(
                f"Attestation spec {attested_spec_id} is not active for model {model_id}"
            )

        attested_dataset_hash = attestation_payload.get("dataset_hash")
        if attested_dataset_hash and str(attested_dataset_hash) != str(
            active_spec.get("dataset_version")
        ):
            raise AttestationSpecSupersededError(
                f"Attestation dataset {attested_dataset_hash} does not match active benchmark spec"
            )
