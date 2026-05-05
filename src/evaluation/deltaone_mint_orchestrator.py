"""Orchestration for DeltaOne acceptance -> mint -> canonical score advancement."""

from __future__ import annotations

# Auth-hook note: this orchestrator relies on the evaluator/client passed in and
# does not open direct remote sessions itself.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from src.api.schemas.token_mint import TokenMintResult
from src.api.services.token_mint_hook import TokenMintHook
from src.cli.attestation import create_attestation
from src.evaluation.deltaone_evaluator import DeltaOneDecision, DeltaOneEvaluator
from src.evaluation.event_payload import (
    DELTAONE_ACCEPTANCE_EVENT_VERSION,
    DeltaOneAcceptanceEvent,
    DeltaOneGuardrailBreach,
    DeltaOneGuardrailSummary,
    EventPayloadError,
    make_idempotency_key,
    to_basis_points,
    to_micro_usdc,
)
from src.evaluation.guardrails import evaluate_guardrails
from src.evaluation.schema import AcceptanceDecision, ComparatorResult, GuardrailResult
from src.evaluation.spec_translation import RuntimeGuardrailSpec
from src.evaluation.tags import ACTUAL_COST_TAG, EVAL_SPEC_ID_TAG, PROJECTED_COST_TAG
from src.evaluation.webhook_delivery import dispatch_deltaone_webhook_event
from src.events.schemas import MintRequest, MintRequestContributor, MintRequestEvaluation
from src.utils.metric_naming import derive_mlflow_name

logger = logging.getLogger(__name__)

DELTAONE_ACHIEVED_EVENT = "deltaone.achieved"
DELTAONE_MINTED_EVENT = "deltaone.minted"

# Tag keys used to resolve model_id_uint from MLflow run tags
_MODEL_ID_UINT_TAG_KEYS = (
    "hokusai.model_id_uint",
    "model_id_uint",
)

_ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class MlflowClientProtocol(Protocol):
    """Subset of MLflow client operations required for mint orchestration."""

    def get_run(self: MlflowClientProtocol, run_id: str) -> Any: ...

    def set_tag(self: MlflowClientProtocol, run_id: str, key: str, value: str) -> None: ...


class MintRequestPublisherProtocol(Protocol):
    """Minimal protocol for publishing MintRequest messages."""

    def publish(self: MintRequestPublisherProtocol, message: MintRequest) -> None: ...


@dataclass(slots=True)
class MintOutcome:
    """Result payload for a single evaluate->mint processing attempt."""

    status: str
    decision: DeltaOneDecision
    mint_result: TokenMintResult | None = None
    attestation_hash: str | None = None
    canonical_score_advanced: bool = False
    acceptance_event: DeltaOneAcceptanceEvent | None = None


@dataclass
class _EventContext:
    """Internal context carrying all data needed to build a DeltaOneAcceptanceEvent."""

    decision: DeltaOneDecision
    baseline_score: float
    candidate_score: float
    metric_family: str = "proportion"
    primary_metric_mlflow_name: str | None = None
    benchmark_spec_id: str | None = None
    eval_id: str | None = None
    model_id_uint: int | None = None
    delta_threshold_pp: float = 1.0
    guardrail_result: GuardrailResult | None = None
    guardrail_specs: list[RuntimeGuardrailSpec] = field(default_factory=list)
    max_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    # Contributor allocations extracted from spec or run tags (HOK-1276)
    contributors: list[dict[str, Any]] = field(default_factory=list)


class DeltaOneMintOrchestrator:
    """Wire DeltaOne acceptance decisions to token mint operations."""

    _FINAL_MINT_STATUSES = {"success", "dry_run"}

    def __init__(
        self: DeltaOneMintOrchestrator,
        evaluator: DeltaOneEvaluator,
        mint_hook: TokenMintHook,
        mlflow_client: MlflowClientProtocol | None = None,
        mint_request_publisher: MintRequestPublisherProtocol | None = None,
    ) -> None:
        self.evaluator = evaluator
        self.mint_hook = mint_hook
        self._client = mlflow_client or evaluator._client  # noqa: SLF001
        self._mint_request_publisher = mint_request_publisher

    def process_evaluation(
        self: DeltaOneMintOrchestrator,
        run_id: str,
        baseline_run_id: str,
    ) -> MintOutcome:
        """Evaluate candidate/baseline pair and mint token on acceptance."""
        decision = self.evaluator.evaluate(run_id, baseline_run_id)
        if not decision.accepted:
            return MintOutcome(status="not_eligible", decision=decision)
        ctx = self._build_minimal_event_context(decision)
        return self._execute_mint(decision, event_context=ctx)

    def _build_minimal_event_context(
        self: DeltaOneMintOrchestrator,
        decision: DeltaOneDecision,
    ) -> _EventContext:
        """Build minimal _EventContext for the legacy process_evaluation path from MLflow tags."""
        candidate_run = self._client.get_run(decision.run_id)
        candidate_tags = getattr(getattr(candidate_run, "data", None), "tags", None) or {}
        baseline_run = self._client.get_run(decision.baseline_run_id)
        baseline_metrics = getattr(getattr(baseline_run, "data", None), "metrics", None) or {}
        candidate_metrics = getattr(getattr(candidate_run, "data", None), "metrics", None) or {}

        model_id_uint_raw = _first_tag(candidate_tags, _MODEL_ID_UINT_TAG_KEYS)
        model_id_uint: int | None = None
        if model_id_uint_raw is not None:
            try:
                model_id_uint = int(str(model_id_uint_raw))
            except (ValueError, TypeError):
                logger.warning(
                    "event=invalid_model_id_uint run_id=%s value=%r",
                    decision.run_id,
                    model_id_uint_raw,
                )

        eval_id = candidate_tags.get("hokusai.eval_id") or ""
        benchmark_spec_id = candidate_tags.get(EVAL_SPEC_ID_TAG) or ""
        mlflow_name = derive_mlflow_name(decision.metric_name)
        candidate_score = _resolve_metric_value(
            decision.metric_name, mlflow_name, candidate_metrics
        )
        baseline_score = _resolve_metric_value(decision.metric_name, mlflow_name, baseline_metrics)
        delta_threshold_pp = getattr(self.evaluator, "delta_threshold_pp", 1.0)

        actual_cost_usd: float | None = None
        actual_cost_raw = candidate_tags.get(ACTUAL_COST_TAG) or candidate_tags.get(
            PROJECTED_COST_TAG
        )
        if actual_cost_raw is not None:
            try:
                actual_cost_usd = float(actual_cost_raw)
            except (ValueError, TypeError):
                pass

        contributors = _extract_contributors_from_tags(candidate_tags)

        return _EventContext(
            decision=decision,
            baseline_score=baseline_score if baseline_score is not None else 0.0,
            candidate_score=candidate_score if candidate_score is not None else 0.0,
            metric_family="proportion",
            primary_metric_mlflow_name=mlflow_name,
            benchmark_spec_id=benchmark_spec_id,
            eval_id=eval_id,
            model_id_uint=model_id_uint,
            delta_threshold_pp=float(delta_threshold_pp),
            guardrail_result=None,
            guardrail_specs=[],
            max_cost_usd=None,
            actual_cost_usd=actual_cost_usd,
            contributors=contributors,
        )

    def process_evaluation_with_spec(
        self: DeltaOneMintOrchestrator,
        run_id: str,
        baseline_run_id: str,
        spec: dict[str, Any],
    ) -> MintOutcome:
        """Evaluate with benchmark spec — runs primary evaluation then guardrail gating."""
        model_id = str(spec.get("model_id", ""))
        decision = self.evaluator.evaluate_for_model(model_id, run_id, baseline_run_id)

        guardrail_specs = _extract_guardrail_specs(spec)
        candidate_run = self._client.get_run(run_id)
        guardrail_observations = _extract_guardrail_observations(candidate_run, guardrail_specs)
        guardrail_result = evaluate_guardrails(guardrail_observations, guardrail_specs)

        primary_result = _decision_to_comparator_result(decision)
        mint_allowed = decision.accepted and guardrail_result.passed
        blocked_reason = (
            _build_blocked_reason(decision, guardrail_result) if not mint_allowed else None
        )

        acceptance = AcceptanceDecision(
            primary=primary_result,
            guardrail=guardrail_result,
            mint_allowed=mint_allowed,
            blocked_reason=blocked_reason,
        )

        self._persist_guardrail_results(run_id, guardrail_result)
        logger.info(
            "deltaone_acceptance_decision run_id=%s mint_allowed=%s blocked_reason=%s",
            run_id,
            mint_allowed,
            blocked_reason,
        )

        if not mint_allowed:
            status = "guardrail_breach" if not guardrail_result.passed else "not_eligible"
            return MintOutcome(status=status, decision=decision)

        # Build event context from spec and run data for spec-backed path
        ctx = self._build_event_context_from_spec(
            decision=decision,
            spec=spec,
            candidate_run=candidate_run,
            guardrail_result=guardrail_result,
            guardrail_specs=guardrail_specs,
        )

        return self._execute_mint(decision, acceptance.blocked_reason, event_context=ctx)

    def _build_event_context_from_spec(
        self: DeltaOneMintOrchestrator,
        decision: DeltaOneDecision,
        spec: dict[str, Any],
        candidate_run: Any,
        guardrail_result: GuardrailResult,
        guardrail_specs: list[RuntimeGuardrailSpec],
    ) -> _EventContext:
        """Build an _EventContext from spec and run data for spec-backed evaluation path."""
        eval_spec = spec.get("eval_spec") or {}
        primary_metric = eval_spec.get("primary_metric") or {}
        metric_family = str(eval_spec.get("metric_family") or "proportion")

        # Resolve primary metric mlflow name
        primary_metric_name = decision.metric_name
        explicit_mlflow_name = primary_metric.get("mlflow_name")
        primary_metric_mlflow_name = derive_mlflow_name(primary_metric_name, explicit_mlflow_name)

        # Resolve benchmark_spec_id
        candidate_tags = getattr(getattr(candidate_run, "data", None), "tags", None) or {}
        benchmark_spec_id = (
            str(spec.get("spec_id") or "")
            or str(spec.get("id") or "")
            or candidate_tags.get(EVAL_SPEC_ID_TAG)
            or ""
        )

        # Resolve eval_id from candidate run tags
        eval_id = candidate_tags.get("hokusai.eval_id") or ""

        # Resolve model_id_uint from spec or candidate tags
        model_id_uint_raw = (
            spec.get("model_id_uint")
            or spec.get("model_id_numeric")
            or _first_tag(candidate_tags, _MODEL_ID_UINT_TAG_KEYS)
        )
        model_id_uint: int | None = None
        if model_id_uint_raw is not None:
            try:
                model_id_uint = int(str(model_id_uint_raw))
            except (ValueError, TypeError):
                logger.warning(
                    "event=invalid_model_id_uint run_id=%s value=%r",
                    decision.run_id,
                    model_id_uint_raw,
                )

        # Resolve baseline and candidate scores
        candidate_metrics = getattr(getattr(candidate_run, "data", None), "metrics", None) or {}
        baseline_run = self._client.get_run(decision.baseline_run_id)
        baseline_metrics = getattr(getattr(baseline_run, "data", None), "metrics", None) or {}
        candidate_score = _resolve_metric_value(
            primary_metric_name, primary_metric_mlflow_name, candidate_metrics
        )
        baseline_score = _resolve_metric_value(
            primary_metric_name, primary_metric_mlflow_name, baseline_metrics
        )

        # Resolve delta threshold from evaluator
        delta_threshold_pp = getattr(self.evaluator, "delta_threshold_pp", 1.0)

        # Resolve cost fields from spec measurement_policy and candidate tags
        measurement_policy = eval_spec.get("measurement_policy") or {}
        max_cost_usd: float | None = None
        max_cost_raw = measurement_policy.get("max_cost_usd")
        if max_cost_raw is not None:
            try:
                max_cost_usd = float(max_cost_raw)
            except (ValueError, TypeError):
                pass

        actual_cost_usd: float | None = None
        actual_cost_raw = candidate_tags.get(ACTUAL_COST_TAG) or candidate_tags.get(
            PROJECTED_COST_TAG
        )
        if actual_cost_raw is not None:
            try:
                actual_cost_usd = float(actual_cost_raw)
            except (ValueError, TypeError):
                pass

        # Prefer contributors from spec, fall back to candidate run tags
        contributors = _extract_contributors_from_spec(spec)
        if not contributors:
            contributors = _extract_contributors_from_tags(candidate_tags)

        return _EventContext(
            decision=decision,
            baseline_score=baseline_score if baseline_score is not None else 0.0,
            candidate_score=candidate_score if candidate_score is not None else 0.0,
            metric_family=metric_family,
            primary_metric_mlflow_name=primary_metric_mlflow_name,
            benchmark_spec_id=benchmark_spec_id,
            eval_id=eval_id,
            model_id_uint=model_id_uint,
            delta_threshold_pp=float(delta_threshold_pp),
            guardrail_result=guardrail_result,
            guardrail_specs=guardrail_specs,
            max_cost_usd=max_cost_usd,
            actual_cost_usd=actual_cost_usd,
            contributors=contributors,
        )

    def _execute_mint(
        self: DeltaOneMintOrchestrator,
        decision: DeltaOneDecision,
        blocked_reason: str | None = None,
        event_context: _EventContext | None = None,
    ) -> MintOutcome:
        attestation_hash, attestation_payload = self._create_signed_attestation(decision)

        # Build acceptance event before any mint side-effects so malformed payloads fail early
        # and before the webhook fires to avoid notifying consumers of a mint that won't happen.
        acceptance_event: DeltaOneAcceptanceEvent | None = None
        if event_context is not None:
            try:
                acceptance_event = _build_acceptance_event(
                    ctx=event_context,
                    attestation_hash=attestation_hash,
                )
            except (EventPayloadError, ValueError) as exc:
                logger.error(
                    "event=acceptance_event_build_failed run_id=%s error=%s",
                    decision.run_id,
                    exc,
                )
                raise EventPayloadError(
                    "acceptance_event",
                    f"failed to build event for run {decision.run_id}: {exc}",
                ) from exc

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
                acceptance_event=acceptance_event,
            )

        self._set_mint_tags(
            run_id=decision.run_id,
            status="requested",
            attestation_hash=attestation_hash,
            idempotency_key=(
                acceptance_event.idempotency_key if acceptance_event else attestation_hash
            ),
            audit_ref=None,
            error=None,
        )

        # Build metadata for HOK-1276 handoff; include the serialized acceptance event if available
        mint_metadata: dict[str, Any] = {
            "attestation": attestation_payload,
            "deltaone_decision": self._decision_to_dict(decision),
        }
        if acceptance_event is not None:
            mint_metadata["deltaone_acceptance_event"] = acceptance_event.model_dump()

        mint_result = self.mint_hook.mint(
            model_id=decision.model_id,
            token_id=self._resolve_token_id(decision.model_id),
            delta_value=decision.delta_percentage_points,
            idempotency_key=(
                acceptance_event.idempotency_key if acceptance_event else attestation_hash
            ),
            metadata=mint_metadata,
        )

        self._set_mint_tags(
            run_id=decision.run_id,
            status=mint_result.status,
            attestation_hash=attestation_hash,
            idempotency_key=(
                acceptance_event.idempotency_key if acceptance_event else attestation_hash
            ),
            audit_ref=mint_result.audit_ref,
            error=mint_result.error,
        )

        canonical_score_advanced = False
        if mint_result.status == "success":
            if self._mint_request_publisher is not None and acceptance_event is not None:
                mint_request = _build_mint_request(
                    acceptance_event=acceptance_event,
                    event_context=event_context,
                )
                self._mint_request_publisher.publish(mint_request)
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
            acceptance_event=acceptance_event,
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
        idempotency_key: str,
        audit_ref: str | None,
        error: str | None,
    ) -> None:
        self._client.set_tag(run_id, "hokusai.mint.status", status)
        self._client.set_tag(run_id, "hokusai.mint.attestation_hash", attestation_hash)
        self._client.set_tag(run_id, "hokusai.mint.idempotency_key", idempotency_key)
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

    def _persist_guardrail_results(
        self: DeltaOneMintOrchestrator,
        run_id: str,
        guardrail_result: GuardrailResult,
    ) -> None:
        for breach in guardrail_result.breaches:
            tag_key = f"hokusai.guardrail.{breach.metric_name}.status"
            self._client.set_tag(run_id, tag_key, "fail")
            reason_key = f"hokusai.guardrail.{breach.metric_name}.reason"
            self._client.set_tag(run_id, reason_key, breach.reason[:500])


# ---------------------------------------------------------------------------
# Module-level helpers for process_evaluation_with_spec
# ---------------------------------------------------------------------------


def _extract_guardrail_specs(spec: dict[str, Any]) -> list[RuntimeGuardrailSpec]:
    """Parse RuntimeGuardrailSpec objects from a raw benchmark spec dict."""
    eval_spec = spec.get("eval_spec") or {}
    raw_guardrails = eval_spec.get("guardrails") or []
    result: list[RuntimeGuardrailSpec] = []
    for g in raw_guardrails:
        if not isinstance(g, dict):
            continue
        name = g.get("name", "")
        direction = g.get("direction", "higher_is_better")
        threshold = g.get("threshold")
        blocking = bool(g.get("blocking", True))
        if not name or threshold is None:
            continue
        result.append(
            RuntimeGuardrailSpec(
                name=name,
                direction=direction,
                threshold=float(threshold),
                blocking=blocking,
            )
        )
    return result


def _extract_guardrail_observations(
    candidate_run: Any,
    guardrail_specs: list[RuntimeGuardrailSpec],
) -> dict[str, float]:
    """Extract observed metric values for each guardrail from a candidate MLflow run."""
    metrics = getattr(getattr(candidate_run, "data", None), "metrics", None) or {}
    observations: dict[str, float] = {}
    for spec in guardrail_specs:
        if spec.name in metrics:
            observations[spec.name] = float(metrics[spec.name])
    return observations


def _decision_to_comparator_result(decision: DeltaOneDecision) -> ComparatorResult:
    """Build a ComparatorResult from the fields in a DeltaOneDecision."""
    return ComparatorResult(
        passed=decision.accepted,
        p_value=None,
        effect_size=decision.delta_percentage_points,
        ci_low=decision.ci95_low_percentage_points,
        ci_high=decision.ci95_high_percentage_points,
        details={"source": "deltaone_decision", "reason": decision.reason},
    )


def _build_blocked_reason(
    decision: DeltaOneDecision,
    guardrail_result: GuardrailResult,
) -> str:
    """Build a human-readable blocked_reason string."""
    parts: list[str] = []
    if not decision.accepted:
        parts.append(f"primary_rejected:{decision.reason}")
    for breach in guardrail_result.breaches:
        parts.append(f"guardrail_breach:{breach.metric_name}:{breach.reason}")
    return "; ".join(parts) if parts else "unknown"


def _first_tag(tags: dict[str, str], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty value from tags matching any of keys."""
    for key in keys:
        value = tags.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _resolve_metric_value(
    metric_name: str,
    mlflow_name: str,
    metrics: dict[str, float],
) -> float | None:
    """Resolve a metric value from run metrics using the same three-tier lookup as DeltaOne."""
    from src.utils.metric_naming import derive_mlflow_name as _derive  # noqa: PLC0415

    normalized = _derive(metric_name)
    if mlflow_name and mlflow_name in metrics:
        return float(metrics[mlflow_name])
    if normalized in metrics:
        return float(metrics[normalized])
    if metric_name in metrics:
        return float(metrics[metric_name])
    return None


def _build_guardrail_summary(
    guardrail_result: GuardrailResult,
    guardrail_specs: list[RuntimeGuardrailSpec],
    metric_family: str,
) -> DeltaOneGuardrailSummary:
    """Convert a GuardrailResult into a DeltaOneGuardrailSummary for the acceptance event."""
    blocking_total = sum(1 for s in guardrail_specs if s.blocking)
    blocking_breaches = list(guardrail_result.breaches)
    guardrails_passed = blocking_total - len(blocking_breaches)

    breach_models: list[DeltaOneGuardrailBreach] = []
    for breach in blocking_breaches:
        try:
            observed_bps = to_basis_points(breach.observed, metric_family)
            threshold_bps = to_basis_points(breach.threshold, metric_family)
        except (EventPayloadError, ValueError) as exc:
            logger.warning(
                "event=guardrail_bps_conversion_failed metric=%s error=%s; defaulting to 0",
                breach.metric_name,
                exc,
            )
            observed_bps = 0
            threshold_bps = 0
        breach_models.append(
            DeltaOneGuardrailBreach(
                metric_name=breach.metric_name,
                observed_bps=observed_bps,
                threshold_bps=threshold_bps,
                observed=breach.observed,
                threshold=breach.threshold,
                direction=breach.direction,
                policy=breach.policy,
                reason=breach.reason,
            )
        )

    return DeltaOneGuardrailSummary(
        total_guardrails=blocking_total,
        guardrails_passed=max(0, guardrails_passed),
        breaches=breach_models,
    )


def _build_acceptance_event(
    ctx: _EventContext,
    attestation_hash: str,
) -> DeltaOneAcceptanceEvent:
    """Construct and validate a DeltaOneAcceptanceEvent from context and attestation hash."""
    decision = ctx.decision

    if ctx.model_id_uint is None:
        raise EventPayloadError(
            "model_id_uint",
            f"model_id_uint is required for DeltaOneAcceptanceEvent but was not found "
            f"in spec or candidate run tags for model={decision.model_id} run={decision.run_id}",
        )

    if not ctx.eval_id:
        raise EventPayloadError(
            "eval_id",
            f"eval_id is required for DeltaOneAcceptanceEvent but tag 'hokusai.eval_id' "
            f"was absent from run {decision.run_id}",
        )

    if not ctx.benchmark_spec_id:
        raise EventPayloadError(
            "benchmark_spec_id",
            f"benchmark_spec_id is required but was absent from spec and run tags "
            f"for run {decision.run_id}",
        )

    metric_family = ctx.metric_family
    baseline_bps = to_basis_points(ctx.baseline_score, metric_family)
    candidate_bps = to_basis_points(ctx.candidate_score, metric_family)
    delta_bps = candidate_bps - baseline_bps
    if delta_bps < 0:
        logger.warning(
            "event=negative_delta_bps run_id=%s candidate_bps=%d baseline_bps=%d delta_bps=%d"
            " — likely metric resolution mismatch; Pydantic will reject this event",
            decision.run_id,
            candidate_bps,
            baseline_bps,
            delta_bps,
        )

    # delta_threshold_bps derived from pp threshold (proportion only for v1)
    delta_threshold_bps = to_basis_points(min(ctx.delta_threshold_pp / 100.0, 1.0), metric_family)

    # Normalize attestation hash to 0x-prefixed form
    norm_att_hash = (
        attestation_hash if attestation_hash.startswith("0x") else f"0x{attestation_hash}"
    )

    idempotency_key = make_idempotency_key(ctx.model_id_uint, ctx.eval_id, norm_att_hash)

    mlflow_name = ctx.primary_metric_mlflow_name or derive_mlflow_name(decision.metric_name)

    guardrail_summary: DeltaOneGuardrailSummary
    if ctx.guardrail_result is not None:
        guardrail_summary = _build_guardrail_summary(
            ctx.guardrail_result, ctx.guardrail_specs, metric_family
        )
    else:
        guardrail_summary = DeltaOneGuardrailSummary(
            total_guardrails=0, guardrails_passed=0, breaches=[]
        )

    max_cost_micro = to_micro_usdc(
        Decimal(str(ctx.max_cost_usd)) if ctx.max_cost_usd is not None else None
    )
    actual_cost_micro = to_micro_usdc(
        Decimal(str(ctx.actual_cost_usd)) if ctx.actual_cost_usd is not None else None
    )

    return DeltaOneAcceptanceEvent(
        event_version=DELTAONE_ACCEPTANCE_EVENT_VERSION,
        model_id=decision.model_id,
        model_id_uint=str(ctx.model_id_uint),
        eval_id=ctx.eval_id,
        mlflow_run_id=decision.run_id,
        benchmark_spec_id=ctx.benchmark_spec_id,
        primary_metric_name=decision.metric_name,
        primary_metric_mlflow_name=mlflow_name,
        metric_family=metric_family,
        baseline_score_bps=baseline_bps,
        candidate_score_bps=candidate_bps,
        delta_bps=delta_bps,
        delta_threshold_bps=delta_threshold_bps,
        attestation_hash=norm_att_hash,
        idempotency_key=idempotency_key,
        guardrail_summary=guardrail_summary,
        max_cost_usd_micro=max_cost_micro,
        actual_cost_usd_micro=actual_cost_micro,
    )


# ---------------------------------------------------------------------------
# MintRequest helpers (HOK-1276)
# ---------------------------------------------------------------------------


def _extract_contributors_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract contributor wallet+weight records from a benchmark spec dict.

    Looks for spec['contributors'] as a list of dicts with 'wallet_address' and
    optional 'weight' (fractional) or 'weight_bps' (integer bps).  Returns an
    empty list if no valid contributors are found.
    """
    raw = spec.get("contributors")
    if not isinstance(raw, list) or not raw:
        return []
    return _normalize_contributor_list(raw)


def _extract_contributors_from_tags(tags: dict[str, str]) -> list[dict[str, Any]]:
    """Extract contributor wallet+weight records from MLflow run tags.

    Checks the 'hokusai.contributors' tag (JSON array) for wallet_address entries.
    Returns an empty list if the tag is absent or malformed.
    """
    raw_json = tags.get("hokusai.contributors")
    if not raw_json:
        return []
    try:
        raw = json.loads(raw_json)
    except (json.JSONDecodeError, ValueError):
        logger.warning("event=invalid_contributors_tag value=%r; skipping", raw_json[:200])
        return []
    if not isinstance(raw, list):
        return []
    return _normalize_contributor_list(raw)


def _normalize_contributor_list(raw: list[Any]) -> list[dict[str, Any]]:
    """Normalize a list of raw contributor dicts into validated wallet+weight_bps records.

    Accepts:
      - weight_bps (int, 0-10000) directly
      - weight (float 0-1) converted deterministically to bps

    Returns only entries with valid Ethereum addresses.  Does NOT enforce that
    the total equals 10000 — callers must do that or let MintRequest validation catch it.
    """
    result: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        wallet = entry.get("wallet_address") or entry.get("wallet")
        if not wallet or not isinstance(wallet, str):
            continue
        if not _ETH_ADDRESS_RE.match(wallet):
            continue

        weight_bps: int | None = None
        if "weight_bps" in entry:
            try:
                weight_bps = int(entry["weight_bps"])
            except (TypeError, ValueError):
                pass
        elif "weight" in entry:
            try:
                weight_f = float(entry["weight"])
                # Deterministic bps from fractional weight using ROUND_HALF_EVEN
                from decimal import ROUND_HALF_EVEN, Decimal  # noqa: PLC0415

                weight_bps = int(
                    (Decimal(str(weight_f)) * Decimal("10000")).to_integral_value(
                        rounding=ROUND_HALF_EVEN
                    )
                )
            except (TypeError, ValueError):
                pass

        if weight_bps is not None and 0 <= weight_bps <= 10000:
            result.append({"wallet_address": wallet.lower(), "weight_bps": weight_bps})

    return result


def _build_mint_request(
    acceptance_event: DeltaOneAcceptanceEvent,
    event_context: _EventContext | None,
) -> MintRequest:
    """Build a MintRequest from a validated DeltaOneAcceptanceEvent and optional EventContext.

    Raises EventPayloadError if no valid contributors are available — the schema
    requires at least one contributor and weights must sum to 10000.
    """
    # Extract statistical metadata from event_context.decision if available
    ctx_decision = event_context.decision if event_context is not None else None
    sample_size_baseline: int | None = None
    sample_size_candidate: int | None = None
    ci_low_bps: int | None = None
    ci_high_bps: int | None = None
    statistical_reason: str | None = None

    if ctx_decision is not None:
        sample_size_baseline = ctx_decision.n_baseline if ctx_decision.n_baseline else None
        sample_size_candidate = ctx_decision.n_current if ctx_decision.n_current else None
        statistical_reason = ctx_decision.reason

        metric_family = acceptance_event.metric_family
        if ctx_decision.ci95_low_percentage_points is not None:
            try:
                ci_low_raw = ctx_decision.ci95_low_percentage_points / 100.0
                ci_low_bps = to_basis_points(min(max(ci_low_raw, 0.0), 1.0), metric_family)
            except (EventPayloadError, ValueError):
                ci_low_bps = None
        if ctx_decision.ci95_high_percentage_points is not None:
            try:
                ci_high_raw = ctx_decision.ci95_high_percentage_points / 100.0
                ci_high_bps = to_basis_points(min(max(ci_high_raw, 0.0), 1.0), metric_family)
            except (EventPayloadError, ValueError):
                ci_high_bps = None

    evaluation = MintRequestEvaluation(
        metric_name=acceptance_event.primary_metric_name,
        metric_family=acceptance_event.metric_family,
        baseline_score_bps=acceptance_event.baseline_score_bps,
        new_score_bps=acceptance_event.candidate_score_bps,
        max_cost_usd_micro=acceptance_event.max_cost_usd_micro,
        actual_cost_usd_micro=acceptance_event.actual_cost_usd_micro,
        sample_size_baseline=sample_size_baseline,
        sample_size_candidate=sample_size_candidate,
        ci_low_bps=ci_low_bps,
        ci_high_bps=ci_high_bps,
        statistical_method="bootstrap_ci",
        statistical_reason=statistical_reason,
    )

    # Resolve contributors
    raw_contributors: list[dict[str, Any]] = []
    if event_context is not None:
        raw_contributors = event_context.contributors

    if not raw_contributors:
        raise EventPayloadError(
            "contributors",
            f"no valid contributor wallet allocations found for model={acceptance_event.model_id} "
            f"eval_id={acceptance_event.eval_id}; "
            "populate spec['contributors'] or the 'hokusai.contributors' run tag",
        )

    # Normalize total to exactly 10000 bps (adjust largest weight for rounding remainder)
    contributors_bps = _normalize_weights_to_10000(raw_contributors)

    contributor_models = [
        MintRequestContributor(
            wallet_address=c["wallet_address"],
            weight_bps=c["weight_bps"],
        )
        for c in contributors_bps
    ]

    return MintRequest(
        message_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        model_id=acceptance_event.model_id,
        model_id_uint=acceptance_event.model_id_uint,
        eval_id=acceptance_event.eval_id,
        attestation_hash=acceptance_event.attestation_hash,
        idempotency_key=acceptance_event.idempotency_key,
        evaluation=evaluation,
        contributors=contributor_models,
    )


def _normalize_weights_to_10000(
    contributors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Adjust contributor weight_bps so they sum to exactly 10000.

    Uses a deterministic remainder adjustment: the largest contributor absorbs
    any rounding shortfall/excess (at most ±N-1 bps for N contributors).
    """
    if not contributors:
        return contributors

    total = sum(c["weight_bps"] for c in contributors)
    if total == 10000:
        return contributors

    result = [dict(c) for c in contributors]
    # Find index of contributor with largest weight for remainder adjustment
    max_idx = max(range(len(result)), key=lambda i: result[i]["weight_bps"])
    adjustment = 10000 - total
    adjusted = result[max_idx]["weight_bps"] + adjustment
    if 0 <= adjusted <= 10000:
        result[max_idx]["weight_bps"] = adjusted
    # If still invalid after adjustment, leave as-is and let MintRequest validation reject it
    return result
