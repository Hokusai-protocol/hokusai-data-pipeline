"""Orchestration for DeltaOne acceptance -> mint -> canonical score advancement."""

from __future__ import annotations

# Auth-hook note: this orchestrator relies on the evaluator/client passed in and
# does not open direct remote sessions itself.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from src.api.schemas.token_mint import TokenMintResult
from src.api.services.token_mint_hook import TokenMintHook
from src.cli.attestation import create_attestation
from src.evaluation.deltaone_evaluator import DeltaOneDecision, DeltaOneEvaluator
from src.evaluation.event_payload import (
    DELTAONE_ACCEPTANCE_EVENT_VERSION,
    DeltaOneEventInputs,
    build_deltaone_acceptance_event,
    normalize_attestation_hash,
)
from src.evaluation.guardrails import evaluate_guardrails
from src.evaluation.schema import (
    AcceptanceDecision,
    ComparatorResult,
    GuardrailResult,
)
from src.evaluation.spec_translation import RuntimeGuardrailSpec
from src.evaluation.webhook_delivery import dispatch_deltaone_webhook_event
from src.utils.metric_naming import derive_mlflow_name

logger = logging.getLogger(__name__)

DELTAONE_ACHIEVED_EVENT = "deltaone.achieved"
DELTAONE_MINTED_EVENT = "deltaone.minted"

# Tag/param key fallbacks used to resolve on-chain event fields when the caller
# does not pass an explicit benchmark spec.
_MODEL_ID_UINT_KEYS = (
    "hokusai.model_id_uint",
    "model_id_uint",
)
_EVAL_ID_KEYS = (
    "hokusai.eval_id",
    "eval_id",
)
_BENCHMARK_SPEC_ID_KEYS = (
    "hokusai.benchmark_spec_id",
    "benchmark_spec_id",
)
_MAX_COST_KEYS = (
    "hokusai.cost.max_usd",
    "max_cost_usd",
)
_ACTUAL_COST_KEYS = (
    "hokusai.cost.actual_usd",
    "actual_cost_usd",
)


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
    idempotency_key: str | None = None


@dataclass(slots=True)
class _DeltaOneEventContext:
    """Bundle of resolved facts the orchestrator threads into the event builder."""

    spec: dict[str, Any] | None
    guardrail_result: GuardrailResult
    guardrail_total: int
    candidate_run: Any
    baseline_run: Any


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
        candidate_run = self._client.get_run(decision.run_id)
        baseline_run = self._client.get_run(decision.baseline_run_id)
        context = _DeltaOneEventContext(
            spec=None,
            guardrail_result=GuardrailResult(passed=True, breaches=()),
            guardrail_total=0,
            candidate_run=candidate_run,
            baseline_run=baseline_run,
        )
        return self._execute_mint(decision, event_context=context)

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

        baseline_run = self._client.get_run(baseline_run_id)
        context = _DeltaOneEventContext(
            spec=spec,
            guardrail_result=guardrail_result,
            guardrail_total=len(guardrail_specs),
            candidate_run=candidate_run,
            baseline_run=baseline_run,
        )
        return self._execute_mint(decision, acceptance.blocked_reason, event_context=context)

    def _execute_mint(
        self: DeltaOneMintOrchestrator,
        decision: DeltaOneDecision,
        blocked_reason: str | None = None,
        event_context: _DeltaOneEventContext | None = None,
    ) -> MintOutcome:
        attestation_hash, attestation_payload = self._create_signed_attestation(decision)
        canonical_hash = normalize_attestation_hash(attestation_hash)

        event = self._build_acceptance_event(
            decision=decision,
            attestation_hash=canonical_hash,
            event_context=event_context,
        )
        idempotency_key = event.idempotency_key

        dispatch_deltaone_webhook_event(
            event_type=DELTAONE_ACHIEVED_EVENT,
            payload=event.model_dump(mode="json"),
        )

        if self._already_finalized_mint(decision.run_id, canonical_hash):
            synthetic_result = TokenMintResult(
                status="success",
                audit_ref="existing_mint",
                timestamp=datetime.now(timezone.utc),
            )
            dispatch_deltaone_webhook_event(
                event_type=DELTAONE_MINTED_EVENT,
                payload=self._build_minted_payload(
                    decision, canonical_hash, idempotency_key, synthetic_result
                ),
            )
            return MintOutcome(
                status="success",
                decision=decision,
                mint_result=synthetic_result,
                attestation_hash=canonical_hash,
                canonical_score_advanced=False,
                idempotency_key=idempotency_key,
            )

        self._set_mint_tags(
            run_id=decision.run_id,
            status="requested",
            attestation_hash=canonical_hash,
            idempotency_key=idempotency_key,
            audit_ref=None,
            error=None,
        )

        mint_result = self.mint_hook.mint(
            model_id=decision.model_id,
            token_id=self._resolve_token_id(decision.model_id),
            delta_value=decision.delta_percentage_points,
            idempotency_key=idempotency_key,
            metadata={
                "attestation": attestation_payload,
                "deltaone_decision": self._decision_to_dict(decision),
                "deltaone_event": event.model_dump(mode="json"),
            },
        )

        self._set_mint_tags(
            run_id=decision.run_id,
            status=mint_result.status,
            attestation_hash=canonical_hash,
            idempotency_key=idempotency_key,
            audit_ref=mint_result.audit_ref,
            error=mint_result.error,
        )

        canonical_score_advanced = False
        if mint_result.status == "success":
            self._advance_canonical_score(decision)
            canonical_score_advanced = True

        dispatch_deltaone_webhook_event(
            event_type=DELTAONE_MINTED_EVENT,
            payload=self._build_minted_payload(
                decision, canonical_hash, idempotency_key, mint_result
            ),
        )

        return MintOutcome(
            status=mint_result.status,
            decision=decision,
            mint_result=mint_result,
            attestation_hash=canonical_hash,
            canonical_score_advanced=canonical_score_advanced,
            idempotency_key=idempotency_key,
        )

    def _build_acceptance_event(
        self: DeltaOneMintOrchestrator,
        decision: DeltaOneDecision,
        attestation_hash: str,
        event_context: _DeltaOneEventContext | None,
    ) -> Any:
        """Resolve on-chain fields and produce a ``DeltaOneAcceptanceEvent``."""
        candidate_run = (
            event_context.candidate_run
            if event_context is not None
            else self._client.get_run(decision.run_id)
        )
        baseline_run = (
            event_context.baseline_run
            if event_context is not None
            else self._client.get_run(decision.baseline_run_id)
        )
        spec = event_context.spec if event_context is not None else None
        guardrail_result = (
            event_context.guardrail_result
            if event_context is not None
            else GuardrailResult(passed=True, breaches=())
        )
        guardrail_total = event_context.guardrail_total if event_context is not None else 0

        candidate_tags = _run_tags(candidate_run)
        candidate_params = _run_params(candidate_run)
        candidate_metrics = _run_metrics(candidate_run)
        baseline_metrics = _run_metrics(baseline_run)

        eval_spec = (spec or {}).get("eval_spec") or {}
        spec_metadata = (spec or {}).get("metadata") or {}
        primary_metric_spec = eval_spec.get("primary_metric") or {}

        # ----- model_id_uint -----
        model_id_uint = _resolve_field(
            spec_paths=[("model_id_uint",)],
            spec=spec,
            metadata=spec_metadata,
            run_sources=(candidate_tags, candidate_params),
            keys=_MODEL_ID_UINT_KEYS,
        )
        if model_id_uint is None:
            raise ValueError(
                "DeltaOne acceptance event requires model_id_uint. "
                "Provide spec['model_id_uint'] or set tag/param "
                "'hokusai.model_id_uint' on the candidate run."
            )

        # ----- eval_id -----
        eval_id = _first_present(candidate_tags, _EVAL_ID_KEYS) or _first_present(
            candidate_params, _EVAL_ID_KEYS
        )
        if eval_id is None:
            raise ValueError(
                "DeltaOne acceptance event requires eval_id. Set tag/param "
                "'hokusai.eval_id' on the candidate run."
            )

        # ----- benchmark_spec_id -----
        spec_id = _resolve_field(
            spec_paths=[("spec_id",)],
            spec=spec,
            metadata=spec_metadata,
            run_sources=(candidate_tags, candidate_params),
            keys=_BENCHMARK_SPEC_ID_KEYS,
        )
        if spec_id is None:
            raise ValueError(
                "DeltaOne acceptance event requires benchmark_spec_id. Provide "
                "spec['spec_id'] or set tag/param 'hokusai.benchmark_spec_id'."
            )

        # ----- primary metric names -----
        primary_metric_name = (
            primary_metric_spec.get("name") if primary_metric_spec else None
        ) or decision.metric_name
        primary_metric_mlflow_name = (
            primary_metric_spec.get("mlflow_name") if primary_metric_spec else None
        ) or derive_mlflow_name(primary_metric_name)

        # ----- metric family -----
        family_value = eval_spec.get("metric_family")
        if hasattr(family_value, "value"):  # StatisticalFamily enum
            metric_family = family_value.value
        else:
            metric_family = family_value or "proportion"

        # ----- scores -----
        candidate_score = _lookup_metric(
            candidate_metrics, primary_metric_mlflow_name, primary_metric_name
        )
        baseline_score = _lookup_metric(
            baseline_metrics, primary_metric_mlflow_name, primary_metric_name
        )

        # ----- delta threshold -----
        threshold = primary_metric_spec.get("threshold")
        if threshold is None:
            # DeltaOneEvaluator stores threshold in percentage points; convert
            # to the [0,1] proportional band the bps helper expects.
            threshold = float(getattr(self.evaluator, "delta_threshold_pp", 0.0)) / 100.0

        # ----- costs -----
        max_cost = _resolve_field(
            spec_paths=[("eval_spec", "cost_policy", "max_cost_usd"), ("max_cost_usd",)],
            spec=spec,
            metadata=spec_metadata,
            run_sources=(candidate_tags, candidate_params),
            keys=_MAX_COST_KEYS,
        )
        actual_cost = _resolve_field(
            spec_paths=[("actual_cost_usd",)],
            spec=spec,
            metadata=spec_metadata,
            run_sources=(candidate_metrics, candidate_tags, candidate_params),
            keys=_ACTUAL_COST_KEYS,
        )

        inputs = DeltaOneEventInputs(
            model_id=decision.model_id,
            model_id_uint=model_id_uint,
            eval_id=str(eval_id),
            mlflow_run_id=decision.run_id,
            benchmark_spec_id=str(spec_id),
            primary_metric_name=str(primary_metric_name),
            primary_metric_mlflow_name=str(primary_metric_mlflow_name),
            metric_family=str(metric_family),
            baseline_score=float(baseline_score),
            candidate_score=float(candidate_score),
            delta_threshold=float(threshold),
            attestation_hash=attestation_hash,
            guardrail_total=int(guardrail_total),
            guardrail_result=guardrail_result,
            max_cost_usd=max_cost if max_cost is not None else 0,
            actual_cost_usd=actual_cost if actual_cost is not None else 0,
            evaluated_at=decision.evaluated_at.isoformat(),
        )
        return build_deltaone_acceptance_event(inputs)

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
    def _build_minted_payload(
        decision: DeltaOneDecision,
        attestation_hash: str,
        idempotency_key: str,
        mint_result: TokenMintResult,
    ) -> dict[str, Any]:
        return {
            "event_type": DELTAONE_MINTED_EVENT,
            "event_version": DELTAONE_ACCEPTANCE_EVENT_VERSION,
            "run_id": decision.run_id,
            "baseline_run_id": decision.baseline_run_id,
            "model_id": decision.model_id,
            "dataset_hash": decision.dataset_hash,
            "metric_name": decision.metric_name,
            "attestation_hash": attestation_hash,
            "idempotency_key": idempotency_key,
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


def _run_tags(run: Any) -> dict[str, Any]:
    return getattr(getattr(run, "data", None), "tags", None) or {}


def _run_params(run: Any) -> dict[str, Any]:
    return getattr(getattr(run, "data", None), "params", None) or {}


def _run_metrics(run: Any) -> dict[str, float]:
    return getattr(getattr(run, "data", None), "metrics", None) or {}


def _first_present(source: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _is_present(value: Any) -> bool:
    """Treat ``None`` and whitespace-only strings as absent."""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _resolve_spec_path(spec: dict[str, Any], path: tuple[str, ...]) -> Any | None:
    cursor: Any = spec
    for part in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
        if cursor is None:
            return None
    return cursor if _is_present(cursor) else None


def _resolve_field(
    *,
    spec_paths: list[tuple[str, ...]],
    spec: dict[str, Any] | None,
    metadata: dict[str, Any],
    run_sources: tuple[dict[str, Any], ...],
    keys: tuple[str, ...],
) -> Any | None:
    """Resolve a field from spec dict-paths, then spec metadata, then run sources."""
    if spec:
        for path in spec_paths:
            value = _resolve_spec_path(spec, path)
            if value is not None:
                return value
    if metadata:
        for key in keys:
            value = metadata.get(key)
            if _is_present(value):
                return value
    for source in run_sources:
        value = _first_present(source, keys)
        if value is not None:
            return value
    return None


def _lookup_metric(
    metrics: dict[str, float],
    mlflow_name: str,
    canonical_name: str,
) -> float:
    if mlflow_name and mlflow_name in metrics:
        return float(metrics[mlflow_name])
    if canonical_name in metrics:
        return float(metrics[canonical_name])
    raise ValueError(
        f"Primary metric not found in run. Tried mlflow_name={mlflow_name!r}, "
        f"canonical={canonical_name!r}; available={sorted(metrics.keys())}"
    )
