"""Orchestration for DeltaOne acceptance -> mint -> canonical score advancement."""

from __future__ import annotations

# Auth-hook note: this orchestrator relies on the evaluator/client passed in and
# does not open direct remote sessions itself.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
import hashlib
import json
import logging
import os
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

from pydantic import ValidationError

from src.api.schemas.token_mint import TokenMintResult
from src.api.services.token_mint_hook import TokenMintHook
from src.cli.attestation import create_attestation, load_attestation_state
from src.evaluation.attribution.contributor_set import (
    ContributorDerivationError,
    derive_contributor_set,
)
from src.evaluation.deltaone_evaluator import DeltaOneDecision, DeltaOneEvaluator
from src.evaluation.event_payload import (
    DELTAONE_ACCEPTANCE_EVENT_VERSION,
    DeltaOneAcceptanceEvent,
    DeltaOneContributorAllocation,
    DeltaOneGuardrailBreach,
    DeltaOneGuardrailSummary,
    EventPayloadError,
    make_idempotency_key,
    to_basis_points,
    to_micro_usdc,
)
from src.evaluation.guardrails import evaluate_guardrails
from src.evaluation.reward_cap import BudgetConfig, RewardCapResult, compute_reward
from src.evaluation.schema import AcceptanceDecision, ComparatorResult, GuardrailResult
from src.evaluation.spec_translation import RuntimeGuardrailSpec
from src.evaluation.tags import (
    ACTUAL_COST_TAG,
    ATTRIBUTION_REPORT_ARTIFACT_URI_TAG,
    EVAL_SPEC_ID_TAG,
    PER_ROW_ARTIFACT_URI_TAG,
    PROJECTED_COST_TAG,
    WEIGHT_COMMITMENT_BASELINE_TAG,
    WEIGHT_COMMITMENT_CANDIDATE_TAG,
)
from src.evaluation.webhook_delivery import dispatch_deltaone_webhook_event
from src.events.schemas import MintRequest, MintRequestContributor, MintRequestEvaluation
from src.utils.metric_naming import derive_mlflow_name

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.eip712.mint_authorization import MintRequestSigningConfig

DELTAONE_ACHIEVED_EVENT = "deltaone.achieved"
DELTAONE_MINTED_EVENT = "deltaone.minted"
_MLFLOW_TAG_VALUE_LIMIT = 5000
# HOK-2170: attester-signature validity window. The deadline is set to now + this many
# days at MintRequest assembly and bound into the EIP-712 digest the attester signs;
# DeltaVerifier reverts SignatureExpired once block.timestamp passes it.
MINT_SIGNATURE_DEADLINE_DAYS = 5

# Tag keys used to resolve model_id_uint from MLflow run tags
_MODEL_ID_UINT_TAG_KEYS = (
    "hokusai.model_id_uint",
    "model_id_uint",
)
_ACTUAL_COST_TAG_KEYS = (ACTUAL_COST_TAG, "hokusai.actual_cost_usd")
_PROJECTED_COST_TAG_KEYS = (PROJECTED_COST_TAG, "hokusai.projected_cost_usd")

_ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_AttributionReportLoader = Callable[[dict[str, str]], dict[str, Any] | None]


def read_current_model_head(
    rpc_url: str,
    *,
    contract_address: str,
    model_id_uint: str,
) -> str:
    """Lazy wrapper kept as a test patch point without importing EIP-712 at module load."""
    from src.eip712.onchain_head import read_current_model_head as _read_current_model_head

    return _read_current_model_head(
        rpc_url,
        contract_address=contract_address,
        model_id_uint=model_id_uint,
    )


def read_attester_threshold(
    rpc_url: str,
    *,
    contract_address: str,
) -> int:
    """Read the current on-chain attester threshold."""
    from src.eip712.onchain_head import read_attester_threshold as _read_attester_threshold

    return _read_attester_threshold(rpc_url, contract_address=contract_address)


def read_is_attester(
    rpc_url: str,
    *,
    contract_address: str,
    address: str,
) -> bool:
    """Check whether an address is currently registered as an attester."""
    from src.eip712.onchain_head import read_is_attester as _read_is_attester

    return _read_is_attester(rpc_url, contract_address=contract_address, address=address)


def build_mint_request_for_run(client: Any, run_id: str) -> tuple[MintRequest, str]:
    """Reconstruct the canonical MintRequest + on-chain baseline for an accepted run.

    Public seam used by the attest CLI to rebuild the exact typed data the
    orchestrator will sign at publish time. Reads the chain head fresh so a
    rebuilt typed-data digest reflects current state, not a frozen MLflow tag.
    """
    run = client.get_run(run_id)
    tags = getattr(getattr(run, "data", None), "tags", None) or {}
    metrics = getattr(getattr(run, "data", None), "metrics", None) or {}

    decision = _decision_from_run_tags(tags, run_id=run_id)
    baseline_run = client.get_run(decision.baseline_run_id)
    baseline_metrics = getattr(getattr(baseline_run, "data", None), "metrics", None) or {}

    mlflow_name = derive_mlflow_name(decision.metric_name)
    baseline_score = (
        _resolve_metric_value(decision.metric_name, mlflow_name, baseline_metrics) or 0.0
    )
    candidate_score = _resolve_metric_value(decision.metric_name, mlflow_name, metrics) or 0.0
    rpc_url = (os.getenv("ETH_RPC_URL") or "").strip()
    verifying_contract = (os.getenv("MINT_VERIFYING_CONTRACT") or "").strip()
    if not rpc_url or not verifying_contract:
        raise EventPayloadError(
            "baseline_commitment",
            "ETH_RPC_URL and MINT_VERIFYING_CONTRACT must be set to rebuild MintRequest typed data",
        )
    baseline_commitment = read_current_model_head(
        rpc_url,
        contract_address=verifying_contract,
        model_id_uint=tags["hokusai.model_id_uint"],
    )
    event_context = _EventContext(
        decision=decision,
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        metric_family=str(tags.get("hokusai.metric_family") or "proportion"),
        primary_metric_mlflow_name=mlflow_name,
        benchmark_spec_id=str(tags.get("hokusai.benchmark_spec_id") or ""),
        eval_id=str(tags.get("hokusai.eval_id") or ""),
        model_id_uint=int(str(tags["hokusai.model_id_uint"])),
        delta_threshold_pp=1.0,
        max_cost_usd=None,
        actual_cost_usd=_resolve_cost_value(tags),
        baseline_commitment=baseline_commitment,
        candidate_commitment=str(tags[WEIGHT_COMMITMENT_CANDIDATE_TAG]),
        contributors=_extract_contributors_from_tags(tags),
    )
    acceptance_event = _build_acceptance_event(
        ctx=event_context,
        attestation_hash=_attestation_hash_from_run_tags(tags, run_id=run_id),
    )
    mint_request = _build_mint_request(
        acceptance_event=acceptance_event,
        event_context=event_context,
        baseline_commitment=baseline_commitment,
        candidate_commitment=event_context.candidate_commitment,
        attester_signatures=[],
    )
    return mint_request, baseline_commitment


def _decision_from_run_tags(tags: dict[str, str], *, run_id: str) -> DeltaOneDecision:
    baseline_run_id = str(tags.get("hokusai.deltaone.baseline_run_id") or "")
    if not baseline_run_id:
        raise ValueError(f"run {run_id} is missing hokusai.deltaone.baseline_run_id")
    evaluated_at = datetime.fromisoformat(str(tags["hokusai.deltaone.evaluated_at"]))
    return DeltaOneDecision(
        accepted=str(tags.get("hokusai.deltaone.accepted") or "").lower() == "true",
        reason=str(tags["hokusai.deltaone.reason"]),
        run_id=run_id,
        baseline_run_id=baseline_run_id,
        model_id=str(tags["hokusai.deltaone.model_id"]),
        dataset_hash=str(tags["hokusai.deltaone.dataset_hash"]),
        metric_name=str(tags["hokusai.deltaone.metric_name"]),
        delta_percentage_points=float(tags["hokusai.deltaone.delta_pp"]),
        ci95_low_percentage_points=float(tags["hokusai.deltaone.ci95_low_pp"]),
        ci95_high_percentage_points=float(tags["hokusai.deltaone.ci95_high_pp"]),
        n_current=int(tags["hokusai.deltaone.n_current"]),
        n_baseline=int(tags["hokusai.deltaone.n_baseline"]),
        evaluated_at=evaluated_at,
    )


def _attestation_hash_from_run_tags(tags: dict[str, str], *, run_id: str) -> str:
    value = (
        tags.get("hokusai_eval.attestation_hash")
        or tags.get("hokusai.mint.attestation_hash")
        or tags.get("hokusai.attestation_hash")
    )
    if not value:
        raise ValueError(f"run {run_id} is missing a persisted attestation hash tag")
    normalized = str(value).lower()
    return normalized if normalized.startswith("0x") else f"0x{normalized}"


class MlflowClientProtocol(Protocol):
    """Subset of MLflow client operations required for mint orchestration."""

    def get_run(self: MlflowClientProtocol, run_id: str) -> Any: ...

    def set_tag(self: MlflowClientProtocol, run_id: str, key: str, value: str) -> None: ...


class MintRequestPublisherProtocol(Protocol):
    """Minimal protocol for publishing MintRequest messages."""

    def publish(self: MintRequestPublisherProtocol, message: MintRequest) -> None: ...


class RewardEntitlementNotifierProtocol(Protocol):
    """Minimal protocol for auth-service reward entitlement delivery."""

    def notify_reward_entitlement(
        self: RewardEntitlementNotifierProtocol,
        *,
        mint_request: MintRequest,
        status: str,
        mint_result: TokenMintResult | None = None,
    ) -> tuple[bool, str | None]: ...


@dataclass(slots=True)
class MintOutcome:
    """Result payload for a single evaluate->mint processing attempt."""

    status: str
    decision: DeltaOneDecision
    mint_result: TokenMintResult | None = None
    attestation_hash: str | None = None
    canonical_score_advanced: bool = False
    acceptance_event: DeltaOneAcceptanceEvent | None = None
    reward_tokens: float | None = None
    reward_capped: bool = False


@dataclass
class _EventContext:
    """Internal context carrying all data needed to build a DeltaOneAcceptanceEvent."""

    decision: DeltaOneDecision
    baseline_score: float
    candidate_score: float
    metric_family: str = "proportion"
    primary_metric_mlflow_name: str | None = None
    benchmark_spec_id: str | None = None
    attribution_report: dict[str, Any] | None = None
    eval_id: str | None = None
    model_id_uint: int | None = None
    delta_threshold_pp: float = 1.0
    guardrail_result: GuardrailResult | None = None
    guardrail_specs: list[RuntimeGuardrailSpec] = field(default_factory=list)
    max_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    baseline_commitment: str | None = None
    candidate_commitment: str | None = None
    # Contributor allocations extracted from spec or run tags (HOK-1276)
    contributors: list[dict[str, Any]] = field(default_factory=list)


class DeltaOneMintOrchestrator:
    """Wire DeltaOne acceptance decisions to token mint operations."""

    _FINAL_MINT_STATUSES = {"success", "published"}

    def __init__(
        self: DeltaOneMintOrchestrator,
        evaluator: DeltaOneEvaluator,
        mint_hook: TokenMintHook,
        mlflow_client: MlflowClientProtocol | None = None,
        mint_request_publisher: MintRequestPublisherProtocol | None = None,
        reward_entitlement_notifier: RewardEntitlementNotifierProtocol | None = None,
        budget_config: BudgetConfig | None = None,
        attribution_report_loader: _AttributionReportLoader | None = None,
    ) -> None:
        self.evaluator = evaluator
        self.mint_hook = mint_hook
        self._client = mlflow_client or evaluator._client  # noqa: SLF001
        self._mint_request_publisher = mint_request_publisher
        self._reward_entitlement_notifier = reward_entitlement_notifier
        if self._reward_entitlement_notifier is None:
            from src.api.services.auth_service_notifier import AuthServiceNotifier

            self._reward_entitlement_notifier = AuthServiceNotifier.from_env()
        self._budget_config = budget_config or BudgetConfig()
        self._attribution_report_loader = (
            attribution_report_loader or _load_attribution_report_from_tags
        )

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

        actual_cost_usd = _resolve_cost_value(candidate_tags)
        baseline_commitment = _resolve_required_commitment_tag(
            candidate_tags.get(WEIGHT_COMMITMENT_BASELINE_TAG),
            logical_name="baseline_commitment",
            mlflow_tag=WEIGHT_COMMITMENT_BASELINE_TAG,
            run_id=decision.run_id,
            model_id=decision.model_id,
        )
        candidate_commitment = _resolve_required_commitment_tag(
            candidate_tags.get(WEIGHT_COMMITMENT_CANDIDATE_TAG),
            logical_name="candidate_commitment",
            mlflow_tag=WEIGHT_COMMITMENT_CANDIDATE_TAG,
            run_id=decision.run_id,
            model_id=decision.model_id,
        )

        attribution_report = self._load_attribution_report(
            candidate_tags,
            decision.run_id,
            baseline_run_id=decision.baseline_run_id,
            model_id=decision.model_id,
        )
        contributors = self._resolve_contributors(
            candidate_tags=candidate_tags,
            candidate_run_id=decision.run_id,
            spec=None,
            attribution_report=attribution_report,
        )

        return _EventContext(
            decision=decision,
            baseline_score=baseline_score if baseline_score is not None else 0.0,
            candidate_score=candidate_score if candidate_score is not None else 0.0,
            metric_family=str(candidate_tags.get("hokusai.metric_family") or "proportion"),
            primary_metric_mlflow_name=mlflow_name,
            benchmark_spec_id=benchmark_spec_id,
            attribution_report=attribution_report,
            eval_id=eval_id,
            model_id_uint=model_id_uint,
            delta_threshold_pp=float(delta_threshold_pp),
            guardrail_result=None,
            guardrail_specs=[],
            max_cost_usd=None,
            actual_cost_usd=actual_cost_usd,
            baseline_commitment=baseline_commitment,
            candidate_commitment=candidate_commitment,
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

        actual_cost_usd = _resolve_cost_value(candidate_tags)
        baseline_commitment = _resolve_required_commitment_tag(
            candidate_tags.get(WEIGHT_COMMITMENT_BASELINE_TAG),
            logical_name="baseline_commitment",
            mlflow_tag=WEIGHT_COMMITMENT_BASELINE_TAG,
            run_id=decision.run_id,
            model_id=decision.model_id,
        )
        candidate_commitment = _resolve_required_commitment_tag(
            candidate_tags.get(WEIGHT_COMMITMENT_CANDIDATE_TAG),
            logical_name="candidate_commitment",
            mlflow_tag=WEIGHT_COMMITMENT_CANDIDATE_TAG,
            run_id=decision.run_id,
            model_id=decision.model_id,
        )

        attribution_report = self._load_attribution_report(
            candidate_tags,
            decision.run_id,
            baseline_run_id=decision.baseline_run_id,
            model_id=decision.model_id,
        )
        contributors = self._resolve_contributors(
            candidate_tags=candidate_tags,
            candidate_run_id=decision.run_id,
            spec=spec,
            attribution_report=attribution_report,
        )

        return _EventContext(
            decision=decision,
            baseline_score=baseline_score if baseline_score is not None else 0.0,
            candidate_score=candidate_score if candidate_score is not None else 0.0,
            metric_family=metric_family,
            primary_metric_mlflow_name=primary_metric_mlflow_name,
            benchmark_spec_id=benchmark_spec_id,
            attribution_report=attribution_report,
            eval_id=eval_id,
            model_id_uint=model_id_uint,
            delta_threshold_pp=float(delta_threshold_pp),
            guardrail_result=guardrail_result,
            guardrail_specs=guardrail_specs,
            max_cost_usd=max_cost_usd,
            actual_cost_usd=actual_cost_usd,
            baseline_commitment=baseline_commitment,
            candidate_commitment=candidate_commitment,
            contributors=contributors,
        )

    def _load_attribution_report(
        self: DeltaOneMintOrchestrator,
        candidate_tags: dict[str, str],
        run_id: str,
        *,
        baseline_run_id: str | None = None,
        model_id: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            report = self._attribution_report_loader(candidate_tags)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "event=attribution_report_load_failed run_id=%s error=%s",
                run_id,
                exc,
            )
            report = None
        if report is not None:
            return report
        # Fallback (HOK-2245): no pre-built report tag, so assemble the report in-process
        # from the candidate and baseline per-row artifacts. The orchestrator is the only
        # stage that holds both run ids, so it is where the account-centric report is built.
        if not baseline_run_id:
            return None
        try:
            return self._build_attribution_report_from_per_row(
                candidate_tags=candidate_tags,
                candidate_run_id=run_id,
                baseline_run_id=baseline_run_id,
                model_id=model_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "event=attribution_report_build_failed run_id=%s baseline_run_id=%s error=%s",
                run_id,
                baseline_run_id,
                exc,
            )
            return None

    def _build_attribution_report_from_per_row(
        self: DeltaOneMintOrchestrator,
        *,
        candidate_tags: dict[str, str],
        candidate_run_id: str,
        baseline_run_id: str,
        model_id: str | None,
    ) -> dict[str, Any] | None:
        """Assemble an attribution report from paired candidate/baseline per-row artifacts."""
        candidate_uri = candidate_tags.get(PER_ROW_ARTIFACT_URI_TAG)
        if not candidate_uri:
            return None
        baseline_run = self._client.get_run(baseline_run_id)
        baseline_tags = getattr(getattr(baseline_run, "data", None), "tags", None) or {}
        baseline_uri = baseline_tags.get(PER_ROW_ARTIFACT_URI_TAG)
        if not baseline_uri:
            logger.warning(
                "event=attribution_per_row_missing run_id=%s baseline_run_id=%s",
                candidate_run_id,
                baseline_run_id,
            )
            return None
        candidate_per_row = _read_per_row_artifact(candidate_uri)
        baseline_per_row = _read_per_row_artifact(baseline_uri)
        if candidate_per_row is None or baseline_per_row is None:
            return None
        from src.evaluation.attribution.neighbor_provenance import attribute  # noqa: PLC0415

        report = attribute(
            baseline_per_row,
            candidate_per_row,
            model_id=str(model_id or ""),
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        logger.info(
            "event=attribution_report_built_from_per_row run_id=%s baseline_run_id=%s "
            "contributors=%d",
            candidate_run_id,
            baseline_run_id,
            len(report.get("contributors", [])),
        )
        return report

    def _resolve_contributors(
        self: DeltaOneMintOrchestrator,
        *,
        candidate_tags: dict[str, str],
        candidate_run_id: str,
        spec: dict[str, Any] | None,
        attribution_report: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if attribution_report is not None:
            try:
                return _extract_contributors_from_attribution_report(
                    attribution_report,
                    candidate_run_id=candidate_run_id,
                )
            except ContributorDerivationError as exc:
                raise EventPayloadError(
                    "contributors",
                    "failed to derive contributors from attribution report for "
                    f"run {candidate_run_id}: {exc}",
                ) from exc

        if spec is not None:
            contributors = _extract_contributors_from_spec(spec)
            if contributors:
                return contributors

        return _extract_contributors_from_tags(candidate_tags)

    def _execute_mint(
        self: DeltaOneMintOrchestrator,
        decision: DeltaOneDecision,
        blocked_reason: str | None = None,
        event_context: _EventContext | None = None,
    ) -> MintOutcome:
        _ = blocked_reason
        if self._budget_config.mint_paused:
            return MintOutcome(status="paused", decision=decision)

        reward_result = compute_reward(
            decision.delta_percentage_points,
            tokens_per_delta_one=self._budget_config.tokens_per_delta_one,
            max_reward_per_eval=self._budget_config.max_reward_per_eval,
        )
        self._log_reward_result(decision, reward_result)

        attestation_hash, attestation_payload = self._create_signed_attestation(
            decision,
            benchmark_spec_id=event_context.benchmark_spec_id if event_context else None,
            attribution_report=event_context.attribution_report if event_context else None,
        )

        # Build acceptance event before any mint side-effects so malformed payloads fail early
        # and before the webhook fires to avoid notifying consumers of a mint that won't happen.
        acceptance_event: DeltaOneAcceptanceEvent | None = None
        if event_context is not None:
            try:
                acceptance_event = _build_acceptance_event(
                    ctx=event_context,
                    attestation_hash=attestation_hash,
                )
            except (EventPayloadError, ValidationError, ValueError) as exc:
                logger.error(
                    "event=acceptance_event_build_failed run_id=%s error=%s",
                    decision.run_id,
                    exc,
                )
                raise EventPayloadError(
                    "acceptance_event",
                    f"failed to build event for run {decision.run_id}: {exc}",
                ) from exc
        if acceptance_event is None:
            raise EventPayloadError(
                "acceptance_event",
                f"accepted DeltaOne mint requires an acceptance event for run {decision.run_id}",
            )
        if self._mint_request_publisher is None:
            raise RuntimeError(
                "MintRequestPublisher is required for accepted DeltaOne mint handoff"
            )

        mint_request = self._build_authorized_mint_request(
            decision=decision,
            acceptance_event=acceptance_event,
            event_context=event_context,
        )
        idempotency_key = acceptance_event.idempotency_key
        ceiling_block = self._check_cost_ceiling(
            decision=decision,
            event_context=event_context,
            attestation_hash=attestation_hash,
            acceptance_event=acceptance_event,
            reward_result=reward_result,
        )
        if ceiling_block is not None:
            return ceiling_block

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
                payload=self._build_minted_payload(
                    decision=decision,
                    attestation_hash=attestation_hash,
                    mint_status="success",
                    mint_result=synthetic_result,
                ),
            )
            return MintOutcome(
                status="success",
                decision=decision,
                mint_result=synthetic_result,
                attestation_hash=attestation_hash,
                canonical_score_advanced=False,
                acceptance_event=acceptance_event,
                reward_tokens=reward_result.reward_tokens,
                reward_capped=reward_result.capped,
            )

        self._set_mint_tags(
            run_id=decision.run_id,
            status="requested",
            attestation_hash=attestation_hash,
            idempotency_key=idempotency_key,
        )

        self._mint_request_publisher.publish(mint_request)
        self._set_mint_tags(
            run_id=decision.run_id,
            status="published",
            attestation_hash=attestation_hash,
            idempotency_key=idempotency_key,
        )
        self._notify_reward_entitlement(
            mint_request=mint_request,
            status="pending",
        )
        self._advance_canonical_score(decision)
        canonical_score_advanced = True

        mint_result = self._run_secondary_mint_hook(
            decision=decision,
            attestation_hash=attestation_hash,
            attestation_payload=attestation_payload,
            acceptance_event=acceptance_event,
        )
        if mint_result.vesting_payload() is not None:
            self._notify_reward_entitlement(
                mint_request=mint_request,
                status="claimable",
                mint_result=mint_result,
            )

        dispatch_deltaone_webhook_event(
            event_type=DELTAONE_MINTED_EVENT,
            payload=self._build_minted_payload(
                decision=decision,
                attestation_hash=attestation_hash,
                mint_status="success",
                mint_result=mint_result,
            ),
        )

        return MintOutcome(
            status="success",
            decision=decision,
            mint_result=mint_result,
            attestation_hash=attestation_hash,
            canonical_score_advanced=canonical_score_advanced,
            acceptance_event=acceptance_event,
            reward_tokens=reward_result.reward_tokens,
            reward_capped=reward_result.capped,
        )

    def _check_cost_ceiling(
        self: DeltaOneMintOrchestrator,
        *,
        decision: DeltaOneDecision,
        event_context: _EventContext | None,
        attestation_hash: str,
        acceptance_event: DeltaOneAcceptanceEvent,
        reward_result: RewardCapResult,
    ) -> MintOutcome | None:
        if (
            event_context is None
            or event_context.actual_cost_usd is None
            or self._budget_config.per_eval_budget_ceiling_usd is None
        ):
            return None
        if event_context.actual_cost_usd <= self._budget_config.per_eval_budget_ceiling_usd:
            return None

        logger.warning(
            "event=eval_cost_ceiling_exceeded run_id=%s actual_cost_usd=%.4f "
            "per_eval_budget_ceiling_usd=%.4f",
            decision.run_id,
            event_context.actual_cost_usd,
            self._budget_config.per_eval_budget_ceiling_usd,
        )
        return MintOutcome(
            status="cost_ceiling_exceeded",
            decision=decision,
            attestation_hash=attestation_hash,
            acceptance_event=acceptance_event,
            reward_tokens=reward_result.reward_tokens,
            reward_capped=reward_result.capped,
        )

    def _log_reward_result(
        self: DeltaOneMintOrchestrator,
        decision: DeltaOneDecision,
        reward_result: RewardCapResult,
    ) -> None:
        if reward_result.capped:
            logger.info(
                "event=reward_capped run_id=%s delta_pp=%.4f tokens_per_delta_one=%s "
                "max_reward_per_eval=%s reward_tokens=%.2f",
                decision.run_id,
                decision.delta_percentage_points,
                self._budget_config.tokens_per_delta_one,
                self._budget_config.max_reward_per_eval,
                reward_result.reward_tokens,
            )
            return
        if self._budget_config.max_reward_per_eval is None:
            return
        logger.info(
            "event=reward_cap_checked run_id=%s delta_pp=%.4f max_reward_per_eval=%s "
            "reward_tokens=%.2f",
            decision.run_id,
            decision.delta_percentage_points,
            self._budget_config.max_reward_per_eval,
            reward_result.reward_tokens,
        )

    def _run_secondary_mint_hook(
        self: DeltaOneMintOrchestrator,
        decision: DeltaOneDecision,
        attestation_hash: str,
        attestation_payload: dict[str, Any],
        acceptance_event: DeltaOneAcceptanceEvent,
    ) -> TokenMintResult:
        # The legacy hook remains an audit-side effect only after the durable Redis handoff
        # succeeds. Its dry-run/failed outcomes are recorded, but do not roll back publish.
        mint_metadata: dict[str, Any] = {
            "attestation": attestation_payload,
            "deltaone_decision": self._decision_to_dict(decision),
            "deltaone_acceptance_event": acceptance_event.model_dump(),
        }
        try:
            mint_result = self.mint_hook.mint(
                model_id=decision.model_id,
                token_id=self._resolve_token_id(decision.model_id),
                delta_value=decision.delta_percentage_points,
                idempotency_key=acceptance_event.idempotency_key,
                metadata=mint_metadata,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "event=secondary_mint_hook_failed run_id=%s model_id=%s",
                decision.run_id,
                decision.model_id,
            )
            mint_result = TokenMintResult(
                status="failed",
                audit_ref="secondary_hook_exception",
                timestamp=datetime.now(timezone.utc),
                error=str(exc),
            )

        self._set_legacy_mint_tags(
            run_id=decision.run_id,
            mint_result=mint_result,
        )
        return mint_result

    def _resolve_baseline_commitment(
        self: DeltaOneMintOrchestrator,
        *,
        model_id_uint: str,
        fallback_commitment: str | None,
    ) -> str:
        """Resolve baseline_commitment at publish time.

        Prefers a fresh on-chain read (Phase 6: catch baseline drift between attach
        and publish). Falls back to the registration-time MLflow tag value only when
        on-chain access is unavailable and `MINT_REQUIRE_ONCHAIN_BASELINE` is false.
        """
        rpc_url = (os.getenv("ETH_RPC_URL") or "").strip()
        verifying_contract = (os.getenv("MINT_VERIFYING_CONTRACT") or "").strip()
        require_env = os.getenv("MINT_REQUIRE_ONCHAIN_BASELINE")
        baseline_required = require_env is None or require_env.lower() != "false"
        if rpc_url and verifying_contract:
            return read_current_model_head(
                rpc_url,
                contract_address=verifying_contract,
                model_id_uint=model_id_uint,
            )
        if fallback_commitment is not None:
            logger.warning(
                "event=mint_request_baseline_commitment_fallback model_id_uint=%s",
                model_id_uint,
            )
            return fallback_commitment
        if baseline_required:
            from src.eip712.onchain_head import BaselineUnavailableError

            raise BaselineUnavailableError(
                "ETH_RPC_URL and MINT_VERIFYING_CONTRACT must be configured "
                "to resolve baseline_commitment"
            )
        raise EventPayloadError(
            "baseline_commitment",
            "baseline_commitment is required and no on-chain or fallback commitment was available",
        )

    def _build_authorized_mint_request(
        self: DeltaOneMintOrchestrator,
        *,
        decision: DeltaOneDecision,
        acceptance_event: DeltaOneAcceptanceEvent,
        event_context: _EventContext | None,
    ) -> MintRequest:
        """Build a canonical MintRequest and log the exact contract-bound typed data."""
        if event_context is None:
            raise EventPayloadError(
                "event_context",
                "accepted MintRequest requires event_context to resolve "
                "commitments and sample sizes",
            )

        baseline_commitment = self._resolve_baseline_commitment(
            model_id_uint=acceptance_event.model_id_uint,
            fallback_commitment=event_context.baseline_commitment,
        )
        candidate_commitment = _resolve_candidate_commitment(
            event_context.candidate_commitment,
            acceptance_event.attestation_hash,
        )
        draft_mint_request = _build_mint_request(
            acceptance_event=acceptance_event,
            event_context=event_context,
            baseline_commitment=baseline_commitment,
            candidate_commitment=candidate_commitment,
            attester_signatures=[],
        )
        ordered_signatures = self._resolve_attester_signatures(
            decision=decision,
            draft_mint_request=draft_mint_request,
            baseline_commitment=baseline_commitment,
        )
        return _build_mint_request(
            acceptance_event=acceptance_event,
            event_context=event_context,
            baseline_commitment=baseline_commitment,
            candidate_commitment=candidate_commitment,
            attester_signatures=ordered_signatures,
        )

    def _resolve_attester_signatures(
        self: DeltaOneMintOrchestrator,
        *,
        decision: DeltaOneDecision,
        draft_mint_request: MintRequest,
        baseline_commitment: str,
    ) -> list[str]:
        """Load and verify attached attester signatures for this publish attempt."""
        from src.eip712 import build_typed_data, compute_digest, render_for_human

        auth_config = _load_mint_authorization_config()
        typed_data = build_typed_data(draft_mint_request, auth_config)
        signing_digest = f"0x{compute_digest(typed_data).hex()}"
        logger.info(
            "event=mint_authorization_typed_data run_id=%s digest=%s\n%s",
            decision.run_id,
            signing_digest,
            render_for_human(typed_data),
        )
        state = load_attestation_state(self._client, decision.run_id)
        if state is None:
            failure_event = "mint_authorization_required_no_attestation_state"
            failure_detail = "no AttestationState on run; run `attest build` and `attest attach`"
        elif state.digest_hex != signing_digest:
            failure_event = "mint_authorization_required_digest_mismatch"
            failure_detail = (
                "AttestationState digest does not match publish-time digest; "
                "run inputs changed after `attest build`"
            )
        elif not state.signatures:
            failure_event = "mint_authorization_required_no_signatures"
            failure_detail = "AttestationState has no signatures; run `attest attach`"
        else:
            failure_event = None
            failure_detail = None
        if failure_event is not None:
            if _attester_signature_required():
                logger.error("event=%s run_id=%s", failure_event, decision.run_id)
                raise _mint_request_signing_error(
                    f"verified attester signatures are required before publish ({failure_detail})"
                )
            logger.warning("event=mint_authorization_skipped_local_dev run_id=%s", decision.run_id)
            return []
        if state.baseline_commitment != baseline_commitment:
            logger.error(
                "event=mint_authorization_baseline_drift_post_attach run_id=%s "
                "attached_baseline=%s onchain_baseline=%s",
                decision.run_id,
                state.baseline_commitment,
                baseline_commitment,
            )
            raise _mint_request_signing_error(
                "attestation baseline drifted between attach and publish; " "rebuild and re-attach"
            )
        return _verify_attestation_state(typed_data, signatures=state.signatures)

    def _notify_reward_entitlement(
        self: DeltaOneMintOrchestrator,
        *,
        mint_request: MintRequest,
        status: str,
        mint_result: TokenMintResult | None = None,
    ) -> None:
        notifier = self._reward_entitlement_notifier
        if notifier is None:
            return
        delivered, error = notifier.notify_reward_entitlement(
            mint_request=mint_request,
            status=status,
            mint_result=mint_result,
        )
        if not delivered:
            logger.warning(
                (
                    "event=reward_entitlement_notification_failed "
                    "idempotency_key=%s status=%s error=%s"
                ),
                mint_request.idempotency_key,
                status,
                error,
            )

    def _create_signed_attestation(
        self: DeltaOneMintOrchestrator,
        decision: DeltaOneDecision,
        *,
        benchmark_spec_id: str | None = None,
        attribution_report: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        attribution_report_hash: str | None = None
        if attribution_report is not None:
            canonical_report = json.dumps(
                attribution_report,
                sort_keys=True,
                separators=(",", ":"),
            )
            attribution_report_hash = hashlib.sha256(canonical_report.encode("utf-8")).hexdigest()
        return create_attestation(
            model_id=decision.model_id,
            eval_spec="deltaone",
            provider="mlflow",
            seed=None,
            temperature=None,
            results=self._decision_to_dict(decision),
            benchmark_spec_id=benchmark_spec_id or None,
            dataset_hash=decision.dataset_hash,
            attribution_report_hash=attribution_report_hash,
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
    ) -> None:
        self._client.set_tag(run_id, "hokusai.mint.status", status)
        self._client.set_tag(run_id, "hokusai.mint.attestation_hash", attestation_hash)
        self._client.set_tag(run_id, "hokusai.mint.idempotency_key", idempotency_key)
        self._client.set_tag(
            run_id,
            "hokusai.mint.updated_at",
            datetime.now(timezone.utc).isoformat(),
        )

    def _set_legacy_mint_tags(
        self: DeltaOneMintOrchestrator,
        run_id: str,
        mint_result: TokenMintResult,
    ) -> None:
        self._client.set_tag(run_id, "hokusai.mint.legacy_status", mint_result.status)
        self._client.set_tag(
            run_id,
            "hokusai.mint.legacy_updated_at",
            datetime.now(timezone.utc).isoformat(),
        )
        self._client.set_tag(run_id, "hokusai.mint.legacy_audit_ref", mint_result.audit_ref or "")
        self._client.set_tag(run_id, "hokusai.mint.legacy_error", mint_result.error or "")

        vesting_payload = mint_result.vesting_payload()
        if vesting_payload is None:
            return

        for field_name, value in vesting_payload.items():
            tag_key = f"hokusai.mint.vesting.{field_name}"
            if field_name == "vesting_config":
                serialized = json.dumps(value, separators=(",", ":"), sort_keys=True)
                if len(serialized) > _MLFLOW_TAG_VALUE_LIMIT:
                    logger.warning(
                        "event=mint_vesting_config_truncated run_id=%s limit=%s",
                        run_id,
                        _MLFLOW_TAG_VALUE_LIMIT,
                    )
                    serialized = f"{serialized[: _MLFLOW_TAG_VALUE_LIMIT - 12]}...[truncated]"
                self._client.set_tag(run_id, "hokusai.mint.vesting.config_json", serialized)
                continue
            self._client.set_tag(run_id, tag_key, str(value))

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
        mint_status: str,
        mint_result: TokenMintResult,
    ) -> dict[str, Any]:
        payload = {
            "event_type": DELTAONE_MINTED_EVENT,
            "run_id": decision.run_id,
            "baseline_run_id": decision.baseline_run_id,
            "model_id": decision.model_id,
            "dataset_hash": decision.dataset_hash,
            "metric_name": decision.metric_name,
            "attestation_hash": attestation_hash,
            "mint_status": mint_status,
            "legacy_mint_status": mint_result.status,
            "legacy_mint_audit_ref": mint_result.audit_ref,
            "legacy_mint_error": mint_result.error,
            "minted_at": mint_result.timestamp.isoformat(),
        }
        vesting_payload = mint_result.vesting_payload()
        if vesting_payload is not None:
            payload["vesting"] = vesting_payload
        return payload

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


def _resolve_cost_value(candidate_tags: dict[str, str]) -> float | None:
    """Resolve actual or projected cost from current or legacy MLflow tag names."""
    actual_cost_raw = _first_tag(candidate_tags, _ACTUAL_COST_TAG_KEYS) or _first_tag(
        candidate_tags,
        _PROJECTED_COST_TAG_KEYS,
    )
    if actual_cost_raw is None:
        return None
    try:
        return float(actual_cost_raw)
    except (ValueError, TypeError):
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

    idempotency_key = make_idempotency_key(ctx.model_id_uint, norm_att_hash)

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

    normalized_contributors = _normalize_weights_to_10000(ctx.contributors)

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
        contributors=[
            DeltaOneContributorAllocation(
                wallet_address=contributor["wallet_address"],
                weight_bps=contributor["weight_bps"],
                submission_id=contributor.get("submission_id"),
                contribution_batch_id=contributor.get("contribution_batch_id"),
                contributor_id=contributor.get("contributor_id"),
            )
            for contributor in normalized_contributors
        ],
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

    Secondary fallback to the attribution report: reads the 'hokusai.contributors' tag (a JSON
    array of {wallet_address, weight_bps} entries). Returns an empty list if the tag is absent
    or malformed.

    The DSPy role->contributor_id inference attribution lives under a different tag
    ('hokusai.contributors_by_role', HOK-2245); a JSON object here is legacy data from before
    that split and cannot produce mint contributors (no wallets/weights), so it is ignored with
    a warning rather than silently dropped.
    """
    raw_json = tags.get("hokusai.contributors")
    if not raw_json:
        return []
    try:
        raw = json.loads(raw_json)
    except (json.JSONDecodeError, ValueError):
        logger.warning("event=invalid_contributors_tag value=%r; skipping", raw_json[:200])
        return []
    if isinstance(raw, dict):
        logger.warning(
            "event=contributors_tag_role_map_ignored value=%r; this is the deprecated "
            "role->id shape, not a mint-contributor array; use the attribution report",
            raw_json[:200],
        )
        return []
    if not isinstance(raw, list):
        return []
    return _normalize_contributor_list(raw)


def _read_per_row_artifact(uri: str) -> Any | None:
    """Download and read a per-row eval parquet artifact into a DataFrame."""
    try:
        import mlflow  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = mlflow.artifacts.download_artifacts(
                artifact_uri=uri,
                dst_path=tmpdir,
            )
            artifact_path = Path(local_path)
            if artifact_path.is_dir():
                artifact_path = artifact_path / "attribution_per_row.parquet"
            return pd.read_parquet(artifact_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("event=per_row_artifact_load_failed uri=%s error=%s", uri, exc)
        return None


def _load_attribution_report_from_artifact(uri: str) -> dict[str, Any] | None:
    """Download and parse an attribution report artifact from MLflow."""
    try:
        import mlflow  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = mlflow.artifacts.download_artifacts(
                artifact_uri=uri,
                dst_path=tmpdir,
            )
            artifact_path = Path(local_path)
            if artifact_path.is_dir():
                artifact_path = artifact_path / "report.json"
            with artifact_path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        logger.warning("event=attribution_report_artifact_load_failed uri=%s error=%s", uri, exc)
        return None

    if not isinstance(payload, dict):
        logger.warning(
            "event=invalid_attribution_report_artifact uri=%s type=%s",
            uri,
            type(payload),
        )
        return None
    return payload


def _load_attribution_report_from_tags(candidate_tags: dict[str, str]) -> dict[str, Any] | None:
    """Resolve an attribution report artifact from candidate run tags."""
    artifact_uri = candidate_tags.get(ATTRIBUTION_REPORT_ARTIFACT_URI_TAG)
    if not artifact_uri:
        return None
    return _load_attribution_report_from_artifact(artifact_uri)


def _extract_contributors_from_attribution_report(
    report: dict[str, Any],
    *,
    candidate_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Derive normalized contributor records from an attribution report."""
    derived = derive_contributor_set(report, candidate_run_id=candidate_run_id)
    contributors: list[dict[str, Any]] = []
    for entry in derived:
        normalized = {
            "wallet_address": entry["wallet"],
            "weight_bps": entry["weight_bps"],
        }
        submission_ids = entry.get("submission_ids") or []
        if submission_ids:
            normalized["submission_id"] = submission_ids[0]
        contributors.append(normalized)
    return contributors


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
        normalized_entry = _normalize_single_contributor(entry)
        if normalized_entry is None:
            continue
        result.append(normalized_entry)

    return sorted(
        result,
        key=lambda item: (
            item["wallet_address"],
            str(item.get("submission_id") or ""),
            str(item.get("contribution_batch_id") or ""),
            str(item.get("contributor_id") or ""),
        ),
    )


def _normalize_single_contributor(entry: Any) -> dict[str, Any] | None:
    """Normalize a single contributor entry when wallet and weight are valid."""
    if not isinstance(entry, dict):
        return None
    wallet = entry.get("wallet_address") or entry.get("wallet")
    if not wallet or not isinstance(wallet, str):
        return None
    if not _ETH_ADDRESS_RE.match(wallet):
        return None

    weight_bps = _coerce_contributor_weight_bps(entry)
    if weight_bps is None or not 0 <= weight_bps <= 10000:
        return None

    normalized_entry: dict[str, Any] = {
        "wallet_address": wallet.lower(),
        "weight_bps": weight_bps,
    }
    normalized_entry.update(_extract_optional_contributor_metadata(entry))
    return normalized_entry


def _coerce_contributor_weight_bps(entry: dict[str, Any]) -> int | None:
    """Return a contributor weight in basis points from either supported input shape."""
    if "weight_bps" in entry:
        try:
            return int(entry["weight_bps"])
        except (TypeError, ValueError):
            return None
    if "weight" not in entry:
        return None
    try:
        weight_f = float(entry["weight"])
        # Deterministic bps from fractional weight using ROUND_HALF_EVEN
        from decimal import ROUND_HALF_EVEN, Decimal  # noqa: PLC0415

        return int(
            (Decimal(str(weight_f)) * Decimal("10000")).to_integral_value(rounding=ROUND_HALF_EVEN)
        )
    except (TypeError, ValueError):
        return None


def _extract_optional_contributor_metadata(entry: dict[str, Any]) -> dict[str, str]:
    """Collect optional contributor traceability fields from snake_case or camelCase input."""
    metadata: dict[str, str] = {}
    field_aliases = {
        "submission_id": ("submission_id", "submissionId"),
        "contribution_batch_id": ("contribution_batch_id", "contributionBatchId"),
        "contributor_id": ("contributor_id", "contributorId"),
    }
    for normalized_key, aliases in field_aliases.items():
        value = next((entry.get(alias) for alias in aliases if entry.get(alias) is not None), None)
        if isinstance(value, str) and value.strip():
            metadata[normalized_key] = value.strip()
    return metadata


def _build_mint_request(
    acceptance_event: DeltaOneAcceptanceEvent,
    event_context: _EventContext | None,
    *,
    baseline_commitment: str | None = None,
    candidate_commitment: str | None = None,
    attester_signatures: list[str] | None = None,
) -> MintRequest:
    """Build a MintRequest from a validated DeltaOneAcceptanceEvent and optional EventContext.

    Raises EventPayloadError if no valid contributors are available — the schema
    requires at least one contributor and weights must sum to 10000.
    """
    # Extract statistical metadata from event_context.decision if available
    ctx_decision = event_context.decision if event_context is not None else None
    metric_family = acceptance_event.metric_family
    sample_size_baseline: int | None = None
    sample_size_candidate: int | None = None
    total_samples: int | None = None
    ci_low_bps: int | None = None
    ci_high_bps: int | None = None
    statistical_reason: str | None = None

    if ctx_decision is None:
        raise EventPayloadError(
            "totalSamples",
            "accepted MintRequest requires event_context.decision to derive "
            "sample_size_candidate and totalSamples",
        )

    sample_size_baseline = _coerce_optional_nonnegative_sample_size(ctx_decision.n_baseline)
    total_samples = _derive_total_samples(ctx_decision.n_current)
    sample_size_candidate = total_samples
    statistical_reason = ctx_decision.reason

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

    _FAMILY_TO_STAT_METHOD: dict[str, str] = {
        "proportion": "two_proportion_z",
        "zero_inflated_continuous": "two_part_zero_inflated",
        "rank_or_ordinal": "mann_whitney_u",
        "continuous": "welch_t",
    }
    resolved_statistical_method = _FAMILY_TO_STAT_METHOD.get(metric_family, "bootstrap_ci")

    effect_size_bps: int | None = None
    if ctx_decision is not None and ctx_decision.delta_percentage_points is not None:
        try:
            effect_size_bps = to_basis_points(
                min(max(ctx_decision.delta_percentage_points / 100.0, 0.0), 1.0),
                metric_family,
            )
        except (EventPayloadError, ValueError):
            effect_size_bps = None

    evaluation = MintRequestEvaluation(
        metric_name=acceptance_event.primary_metric_name,
        metric_family=metric_family,
        baseline_score_bps=acceptance_event.baseline_score_bps,
        new_score_bps=acceptance_event.candidate_score_bps,
        max_cost_usd_micro=acceptance_event.max_cost_usd_micro,
        actual_cost_usd_micro=acceptance_event.actual_cost_usd_micro,
        sample_size_baseline=sample_size_baseline,
        sample_size_candidate=sample_size_candidate,
        ci_low_bps=ci_low_bps,
        ci_high_bps=ci_high_bps,
        effect_size_bps=effect_size_bps,
        statistical_method=resolved_statistical_method,
        statistical_reason=statistical_reason,
    )

    # Resolve contributors
    if not acceptance_event.contributors:
        raise EventPayloadError(
            "contributors",
            f"no valid contributor wallet allocations found for model={acceptance_event.model_id} "
            f"eval_id={acceptance_event.eval_id}; provide a valid attribution report via "
            f"'{ATTRIBUTION_REPORT_ARTIFACT_URI_TAG}' or fall back to spec['contributors'] "
            "or the 'hokusai.contributors' run tag",
        )

    contributor_models = [
        MintRequestContributor(
            wallet_address=contributor.wallet_address,
            weight_bps=contributor.weight_bps,
            submission_id=contributor.submission_id,
            contribution_batch_id=contributor.contribution_batch_id,
            contributor_id=contributor.contributor_id,
        )
        for contributor in acceptance_event.contributors
    ]

    resolved_baseline_commitment = baseline_commitment or _fallback_commitment(
        "baseline", acceptance_event.attestation_hash
    )
    resolved_candidate_commitment = _resolve_candidate_commitment(
        candidate_commitment,
        acceptance_event.attestation_hash,
    )
    resolved_attester_signatures = (
        attester_signatures
        if attester_signatures is not None
        else ([] if not _attester_signature_required() else None)
    )
    if resolved_attester_signatures is None:
        raise _mint_request_signing_error(
            "attester_signatures must be supplied when attester signatures are required"
        )

    return MintRequest(
        message_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        model_id=acceptance_event.model_id,
        model_id_uint=acceptance_event.model_id_uint,
        eval_id=acceptance_event.eval_id,
        benchmark_spec_id=acceptance_event.benchmark_spec_id,
        dataset_hash=_normalise_to_0x_sha256(ctx_decision.dataset_hash, field="dataset_hash"),
        attestation_hash=acceptance_event.attestation_hash,
        idempotency_key=acceptance_event.idempotency_key,
        baseline_commitment=resolved_baseline_commitment,
        candidate_commitment=resolved_candidate_commitment,
        attester_signatures=resolved_attester_signatures,
        total_samples=total_samples,
        deadline=int(
            (datetime.now(timezone.utc) + timedelta(days=MINT_SIGNATURE_DEADLINE_DAYS)).timestamp()
        ),
        evaluation=evaluation,
        contributors=contributor_models,
    )


def _coerce_optional_nonnegative_sample_size(value: Any) -> int | None:
    """Return a non-negative integer sample size, or None when missing/invalid."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _derive_total_samples(value: Any) -> int:
    """Derive the required top-level totalSamples field from decision.n_current."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise EventPayloadError(
            "totalSamples",
            "sample_size_candidate / totalSamples must be a positive integer "
            "derived from decision.n_current",
        )
    if value <= 0:
        raise EventPayloadError(
            "totalSamples",
            f"sample_size_candidate / totalSamples must be >= 1; got {value}",
        )
    return value


def _normalise_to_0x_sha256(value: Any, *, field: str) -> str:
    """Return a canonical 0x-prefixed lowercase SHA-256 hash."""
    if not isinstance(value, str):
        raise EventPayloadError(field, f"expected a string hash, got {type(value).__name__!r}")

    lower = value.lower()
    if lower.startswith("sha256:"):
        bare = lower.removeprefix("sha256:")
    elif lower.startswith("0x"):
        bare = lower.removeprefix("0x")
    else:
        bare = lower

    if len(bare) != 64 or any(char not in "0123456789abcdef" for char in bare):
        raise EventPayloadError(
            field,
            f"expected sha256:<64 lowercase hex> or 0x<64 lowercase hex>, got {value!r}",
        )
    return f"0x{bare}"


def _resolve_required_commitment_tag(
    value: Any,
    *,
    logical_name: str,
    mlflow_tag: str,
    run_id: str,
    model_id: str | None,
) -> str:
    """Normalize a required commitment tag to canonical 0x-prefixed lowercase hex."""
    if value is None or not str(value).strip():
        raise EventPayloadError(
            logical_name,
            f"{logical_name} is required for run {run_id}"
            + (f" model={model_id}" if model_id else "")
            + f"; missing MLflow tag {mlflow_tag!r}",
        )
    raw_value = str(value).strip()
    if raw_value != raw_value.lower():
        raise EventPayloadError(
            logical_name,
            f"{logical_name} on run {run_id}"
            + (f" model={model_id}" if model_id else "")
            + (
                f" from MLflow tag {mlflow_tag!r} must already be lowercase "
                f"canonical hex: {raw_value!r}"
            ),
        )
    try:
        return _normalise_to_0x_sha256(raw_value, field=logical_name)
    except EventPayloadError as exc:
        raise EventPayloadError(
            logical_name,
            f"{logical_name} on run {run_id}"
            + (f" model={model_id}" if model_id else "")
            + f" from MLflow tag {mlflow_tag!r} is invalid: {value!r}",
        ) from exc


def _resolve_candidate_commitment(
    candidate_commitment: str | None,
    attestation_hash: str,
) -> str:
    """Resolve the candidate commitment, preserving tagged values when present."""
    if candidate_commitment is not None:
        return candidate_commitment

    logger.warning("event=mint_request_candidate_commitment_fallback")
    return _fallback_commitment("candidate", attestation_hash)


def _fallback_commitment(label: str, seed: str) -> str:
    """Build a deterministic bytes32 placeholder when offline fixtures omit lineage tags."""
    digest = hashlib.sha256(f"{label}:{seed}".encode()).hexdigest()
    return f"0x{digest}"


def _load_optional_mint_authorization_config() -> MintRequestSigningConfig | None:
    """Backward-compatible shim for older callers."""
    if not _attester_signature_required():
        chain_id = (os.getenv("MINT_CHAIN_ID") or "").strip()
        verifying_contract = (os.getenv("MINT_VERIFYING_CONTRACT") or "").strip()
        if not chain_id or not verifying_contract:
            return None
    return _load_mint_authorization_config()


def _load_mint_authorization_config() -> MintRequestSigningConfig:
    from src.eip712.mint_authorization import MintRequestSigningConfig

    return MintRequestSigningConfig.from_env()


def _attester_signature_required() -> bool:
    return (os.getenv("MINT_REQUIRE_ATTESTER_SIGNATURE") or "").strip().lower() != "false"


def _mint_request_signing_error(message: str) -> EventPayloadError:
    return EventPayloadError("attester_signatures", message)


def _verify_attestation_state(typed_data: dict[str, Any], *, signatures: list[str]) -> list[str]:
    from src.eip712 import validate_signatures_against_registry

    rpc_url = (os.getenv("ETH_RPC_URL") or "").strip()
    verifying_contract = (os.getenv("MINT_VERIFYING_CONTRACT") or "").strip()
    if not rpc_url or not verifying_contract:
        if _attester_signature_required():
            raise _mint_request_signing_error(
                "ETH_RPC_URL and MINT_VERIFYING_CONTRACT are required for attester verification"
            )
        fallback = (os.getenv("MINT_ATTESTER_ADDRESS") or "").strip().lower()
        if not fallback:
            raise _mint_request_signing_error(
                "MINT_ATTESTER_ADDRESS is required for local-dev fallback"
            )

        return validate_signatures_against_registry(
            typed_data,
            signatures,
            registry_check=lambda address: address.lower() == fallback,
            threshold=1,
        )

    threshold = read_attester_threshold(rpc_url, contract_address=verifying_contract)
    return validate_signatures_against_registry(
        typed_data,
        signatures,
        registry_check=lambda address: read_is_attester(
            rpc_url,
            contract_address=verifying_contract,
            address=address,
        ),
        threshold=threshold,
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
