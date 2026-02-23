"""Orchestration for DeltaOne acceptance -> mint -> canonical score advancement."""

from __future__ import annotations

# Auth-hook note: this orchestrator relies on the evaluator/client passed in and
# does not open direct remote sessions itself.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from src.api.schemas.token_mint import TokenMintResult
from src.api.services.token_mint_hook import TokenMintHook
from src.cli.attestation import create_attestation
from src.evaluation.deltaone_evaluator import DeltaOneDecision, DeltaOneEvaluator
from src.evaluation.webhook_delivery import dispatch_deltaone_webhook_event

DELTAONE_ACHIEVED_EVENT = "deltaone.achieved"
DELTAONE_MINTED_EVENT = "deltaone.minted"


class MlflowClientProtocol(Protocol):
    """Subset of MLflow client operations required for mint orchestration."""

    def get_run(self: MlflowClientProtocol, run_id: str) -> Any: ...

    def set_tag(self: MlflowClientProtocol, run_id: str, key: str, value: str) -> None: ...


@dataclass(slots=True)
class MintOutcome:
    """Result payload for a single evaluate->mint processing attempt."""

    status: str
    decision: DeltaOneDecision
    mint_result: TokenMintResult | None = None
    attestation_hash: str | None = None
    canonical_score_advanced: bool = False


class DeltaOneMintOrchestrator:
    """Wire DeltaOne acceptance decisions to token mint operations."""

    _FINAL_MINT_STATUSES = {"success", "dry_run"}

    def __init__(
        self: DeltaOneMintOrchestrator,
        evaluator: DeltaOneEvaluator,
        mint_hook: TokenMintHook,
        mlflow_client: MlflowClientProtocol | None = None,
    ) -> None:
        self.evaluator = evaluator
        self.mint_hook = mint_hook
        self._client = mlflow_client or evaluator._client  # noqa: SLF001

    def process_evaluation(
        self: DeltaOneMintOrchestrator,
        run_id: str,
        baseline_run_id: str,
    ) -> MintOutcome:
        """Evaluate candidate/baseline pair and mint token on acceptance."""
        decision = self.evaluator.evaluate(run_id, baseline_run_id)
        if not decision.accepted:
            return MintOutcome(status="not_eligible", decision=decision)

        attestation_hash, attestation_payload = self._create_signed_attestation(decision)
        dispatch_deltaone_webhook_event(
            event_type=DELTAONE_ACHIEVED_EVENT,
            payload=self._build_achieved_payload(decision, attestation_hash),
        )

        if self._already_finalized_mint(decision.run_id, attestation_hash):
            synthetic_result = TokenMintResult(
                status="success",
                audit_ref="existing_mint",
                timestamp=datetime.now(timezone.utc),
            )
            dispatch_deltaone_webhook_event(
                event_type=DELTAONE_MINTED_EVENT,
                payload=self._build_minted_payload(decision, attestation_hash, synthetic_result),
            )
            return MintOutcome(
                status="success",
                decision=decision,
                mint_result=synthetic_result,
                attestation_hash=attestation_hash,
                canonical_score_advanced=False,
            )

        self._set_mint_tags(
            run_id=decision.run_id,
            status="requested",
            attestation_hash=attestation_hash,
            audit_ref=None,
            error=None,
        )

        mint_result = self.mint_hook.mint(
            model_id=decision.model_id,
            token_id=self._resolve_token_id(decision.model_id),
            delta_value=decision.delta_percentage_points,
            idempotency_key=attestation_hash,
            metadata={
                "attestation": attestation_payload,
                "deltaone_decision": self._decision_to_dict(decision),
            },
        )

        self._set_mint_tags(
            run_id=decision.run_id,
            status=mint_result.status,
            attestation_hash=attestation_hash,
            audit_ref=mint_result.audit_ref,
            error=mint_result.error,
        )

        canonical_score_advanced = False
        if mint_result.status == "success":
            self._advance_canonical_score(decision)
            canonical_score_advanced = True

        dispatch_deltaone_webhook_event(
            event_type=DELTAONE_MINTED_EVENT,
            payload=self._build_minted_payload(decision, attestation_hash, mint_result),
        )

        return MintOutcome(
            status=mint_result.status,
            decision=decision,
            mint_result=mint_result,
            attestation_hash=attestation_hash,
            canonical_score_advanced=canonical_score_advanced,
        )

    def _create_signed_attestation(
        self: DeltaOneMintOrchestrator, decision: DeltaOneDecision
    ) -> tuple[str, dict[str, Any]]:
        return create_attestation(
            model_id=decision.model_id,
            eval_spec="deltaone",
            provider="mlflow",
            seed=None,
            temperature=None,
            results=self._decision_to_dict(decision),
        )

    def _resolve_token_id(self: DeltaOneMintOrchestrator, model_id: str) -> str:
        return f"deltaone:{model_id}"

    def _advance_canonical_score(
        self: DeltaOneMintOrchestrator, decision: DeltaOneDecision
    ) -> None:
        run = self._client.get_run(decision.run_id)
        metric_value = float((run.data.metrics or {}).get(decision.metric_name, 0.0))

        self._client.set_tag(decision.run_id, "hokusai.canonical_score", f"{metric_value:.12g}")
        self._client.set_tag(decision.run_id, "hokusai.canonical_score_run_id", decision.run_id)

    def _already_finalized_mint(
        self: DeltaOneMintOrchestrator, run_id: str, attestation_hash: str
    ) -> bool:
        run = self._client.get_run(run_id)
        tags = run.data.tags or {}
        return (
            tags.get("hokusai.mint.attestation_hash") == attestation_hash
            and tags.get("hokusai.mint.status") in self._FINAL_MINT_STATUSES
        )

    def _set_mint_tags(
        self: DeltaOneMintOrchestrator,
        run_id: str,
        status: str,
        attestation_hash: str,
        audit_ref: str | None,
        error: str | None,
    ) -> None:
        self._client.set_tag(run_id, "hokusai.mint.status", status)
        self._client.set_tag(run_id, "hokusai.mint.attestation_hash", attestation_hash)
        self._client.set_tag(run_id, "hokusai.mint.idempotency_key", attestation_hash)
        self._client.set_tag(
            run_id,
            "hokusai.mint.updated_at",
            datetime.now(timezone.utc).isoformat(),
        )
        if audit_ref:
            self._client.set_tag(run_id, "hokusai.mint.audit_ref", audit_ref)
        if error:
            self._client.set_tag(run_id, "hokusai.mint.error", error)

    @staticmethod
    def _decision_to_dict(decision: DeltaOneDecision) -> dict[str, Any]:
        return {
            "accepted": decision.accepted,
            "reason": decision.reason,
            "run_id": decision.run_id,
            "baseline_run_id": decision.baseline_run_id,
            "model_id": decision.model_id,
            "dataset_hash": decision.dataset_hash,
            "metric_name": decision.metric_name,
            "delta_percentage_points": decision.delta_percentage_points,
            "ci95_low_percentage_points": decision.ci95_low_percentage_points,
            "ci95_high_percentage_points": decision.ci95_high_percentage_points,
            "n_current": decision.n_current,
            "n_baseline": decision.n_baseline,
            "evaluated_at": decision.evaluated_at.isoformat(),
        }

    @staticmethod
    def _build_achieved_payload(
        decision: DeltaOneDecision, attestation_hash: str
    ) -> dict[str, Any]:
        return {
            "event_type": DELTAONE_ACHIEVED_EVENT,
            "run_id": decision.run_id,
            "baseline_run_id": decision.baseline_run_id,
            "model_id": decision.model_id,
            "dataset_hash": decision.dataset_hash,
            "metric_name": decision.metric_name,
            "delta_percentage_points": decision.delta_percentage_points,
            "attestation_hash": attestation_hash,
            "evaluated_at": decision.evaluated_at.isoformat(),
        }

    @staticmethod
    def _build_minted_payload(
        decision: DeltaOneDecision,
        attestation_hash: str,
        mint_result: TokenMintResult,
    ) -> dict[str, Any]:
        return {
            "event_type": DELTAONE_MINTED_EVENT,
            "run_id": decision.run_id,
            "baseline_run_id": decision.baseline_run_id,
            "model_id": decision.model_id,
            "dataset_hash": decision.dataset_hash,
            "metric_name": decision.metric_name,
            "attestation_hash": attestation_hash,
            "mint_status": mint_result.status,
            "mint_audit_ref": mint_result.audit_ref,
            "mint_error": mint_result.error,
            "minted_at": mint_result.timestamp.isoformat(),
        }
