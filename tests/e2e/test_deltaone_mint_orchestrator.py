"""Integration tests for DeltaOne mint orchestration with attestation registry."""

from __future__ import annotations

from datetime import datetime, timezone

import fakeredis
import pytest

from src.api.services.attestation_registry import (
    AttestationAlreadyConsumedError,
    AttestationRegistry,
)
from src.api.services.deltaone_mint_orchestrator import (
    AttestationSpecSupersededError,
    DeltaOneMintOrchestrator,
    MintRequestContext,
)
from src.api.services.score_history_audit import ScoreHistoryAudit
from src.api.services.token_mint_hook import TokenMintHook
from src.evaluation.deltaone_evaluator import DeltaOneDecision


class _SpecResolver:
    def get_active_spec_for_model(self, _model_id: str) -> dict[str, object]:
        return {
            "spec_id": "spec-active",
            "dataset_version": "sha256:" + "a" * 64,
        }


def _decision() -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=True,
        reason="accepted",
        run_id="candidate-run",
        baseline_run_id="baseline-run",
        model_id="model-a",
        dataset_hash="sha256:" + "a" * 64,
        metric_name="accuracy",
        delta_percentage_points=2.5,
        ci95_low_percentage_points=1.2,
        ci95_high_percentage_points=3.8,
        n_current=10000,
        n_baseline=10000,
        evaluated_at=datetime.now(timezone.utc),
    )


def test_mint_orchestrator_consumes_attestation_and_prevents_replay() -> None:
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    orchestrator = DeltaOneMintOrchestrator(
        mint_hook=TokenMintHook(dry_run=True),
        attestation_registry=AttestationRegistry(redis_client=redis_client, ttl_seconds=120),
        benchmark_spec_resolver=_SpecResolver(),
        score_history_audit=ScoreHistoryAudit(redis_client=redis_client),
    )

    request = MintRequestContext(
        token_id="token-a",
        attestation_hash="1" * 64,
        attestation_payload={
            "benchmark_spec_id": "spec-active",
            "dataset_hash": "sha256:" + "a" * 64,
            "attestation_nonce": "nonce-1",
        },
    )

    result = orchestrator.mint_for_decision(decision=_decision(), request=request)
    assert result is not None
    assert result.status == "dry_run"

    history = ScoreHistoryAudit(redis_client=redis_client).list_transitions("model-a")
    assert len(history) == 1
    assert history[0]["attestation_hash"] == "1" * 64

    with pytest.raises(AttestationAlreadyConsumedError):
        orchestrator.mint_for_decision(decision=_decision(), request=request)


def test_mint_orchestrator_rejects_superseded_spec() -> None:
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    orchestrator = DeltaOneMintOrchestrator(
        mint_hook=TokenMintHook(dry_run=True),
        attestation_registry=AttestationRegistry(redis_client=redis_client, ttl_seconds=120),
        benchmark_spec_resolver=_SpecResolver(),
    )

    request = MintRequestContext(
        token_id="token-a",
        attestation_hash="2" * 64,
        attestation_payload={
            "benchmark_spec_id": "spec-old",
            "dataset_hash": "sha256:" + "a" * 64,
            "attestation_nonce": "nonce-2",
        },
    )

    with pytest.raises(AttestationSpecSupersededError):
        orchestrator.mint_for_decision(decision=_decision(), request=request)
