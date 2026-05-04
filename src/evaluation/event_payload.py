"""DeltaOne acceptance event payload schema and helpers.

This module defines the canonical ``deltaone.acceptance/v1`` event the
``DeltaOneMintOrchestrator`` publishes when a candidate run is accepted for
minting.  The shape is engineered for on-chain ``DeltaVerifier`` compatibility:

- All scores are integer basis points (``0..10000``) so they can be packed
  directly into a Solidity ``uint16``/``uint256`` without floating-point
  conversion on chain.
- Cost values are integer USDC micro-units (``1e6`` decimals).
- ``model_id_uint`` is a decimal-encoded ``uint256`` string for ABI parity.
- The event carries a deterministic ``idempotency_key`` that on-chain receivers
  can use to deduplicate replays.

The schema is exposed both as a Pydantic v2 model and as a JSON Schema
artifact (see ``DELTAONE_ACCEPTANCE_EVENT_JSON_SCHEMA``) so downstream services
can validate without importing the orchestrator.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.evaluation.comparators import COMPARATOR_REGISTRY
from src.evaluation.schema import GuardrailBreach, GuardrailResult
from src.utils.metric_naming import derive_mlflow_name

DELTAONE_ACCEPTANCE_EVENT_VERSION = "deltaone.acceptance/v1"

# uint256 max — used to validate model_id_uint and cost overflow.
UINT256_MAX = (1 << 256) - 1

# Maximum bps (100% == 10000 basis points). On-chain DeltaVerifier struct
# packs accuracy into a uint16, so anything above 10000 is rejected here so
# the consumer never has to truncate.
BPS_MAX = 10_000

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_UINT_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: float | int | Decimal | str) -> Decimal:
    """Convert *value* to ``Decimal`` via its string repr, rejecting NaN/Inf."""
    if isinstance(value, bool):
        # bool is an int subclass; reject to avoid silently coercing True->1.
        raise TypeError("Numeric helpers do not accept bool")
    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            raise ValueError(f"Decimal value must be finite, got {value!r}")
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"Float value must be finite, got {value!r}")
        # Use str(float) so we match user-visible precision rather than the
        # binary-exact float value (Decimal(0.1) != Decimal("0.1")).
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Cannot parse {value!r} as Decimal") from exc
        if result.is_nan() or result.is_infinite():
            raise ValueError(f"Decimal value must be finite, got {value!r}")
        return result
    raise TypeError(f"Unsupported numeric type: {type(value).__name__}")


def to_basis_points(value: float | int | Decimal | str, family: str = "proportion") -> int:
    """Convert a normalized acceptance score in ``[0, 1]`` to basis points.

    All conversion is performed through ``Decimal(str(value))`` to avoid binary
    float artifacts.  Half-up rounding is applied so ``0.12345 -> 1235``.

    For ``proportion``, the input domain is ``[0, 1]`` natively (proportion of
    successes).  For non-proportion families, callers MUST normalize their raw
    scores into the ``[0, 1]`` band before invoking this helper; the helper
    deliberately does not invent a default mapping for arbitrary continuous,
    rank, or zero-inflated metrics.

    Args:
    ----
        value: Score in ``[0, 1]`` to convert.
        family: Metric family name.  Must be a key of ``COMPARATOR_REGISTRY``.

    Returns:
    -------
        Integer in ``[0, 10000]``.

    Raises:
    ------
        ValueError: If *value* is NaN/Infinity, negative, > 1.0, or *family*
            is unknown.

    """
    if family not in COMPARATOR_REGISTRY:
        raise ValueError(
            f"Unknown metric_family {family!r}. " f"Known: {sorted(COMPARATOR_REGISTRY.keys())}."
        )

    decimal_value = _to_decimal(value)
    if decimal_value < 0:
        raise ValueError(f"Score must be >= 0, got {value!r}")
    if decimal_value > 1:
        raise ValueError(f"Score must be <= 1.0 for {family} family, got {value!r}")

    bps = (decimal_value * Decimal(BPS_MAX)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    bps_int = int(bps)
    # Defensive bound — quantize+clamp should already keep us in range, but
    # surface tampering loudly rather than silently truncating.
    if not 0 <= bps_int <= BPS_MAX:
        raise ValueError(f"Computed bps {bps_int} out of [0, {BPS_MAX}]")
    return bps_int


def to_micro_usdc(value: float | int | Decimal | str) -> int:
    """Convert a USD value to USDC micro-units (1e6 decimals).

    Examples
    --------
        ``to_micro_usdc(Decimal("2.50")) == 2_500_000``
        ``to_micro_usdc(0)              == 0``

    Negative values, NaN, Infinity, and amounts that overflow ``uint256`` are
    rejected.  Half-up rounding is applied at the micro-unit boundary.

    """
    decimal_value = _to_decimal(value)
    if decimal_value < 0:
        raise ValueError(f"Cost must be >= 0, got {value!r}")

    # Multiplying very large costs by 1e6 can exceed the default Decimal
    # precision (28 digits).  Use a local context wide enough to represent
    # uint256 * 1e6 without InvalidOperation, then bounds-check the result.
    with localcontext() as ctx:
        ctx.prec = 90
        micro = (decimal_value * Decimal(1_000_000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    micro_int = int(micro)
    if micro_int > UINT256_MAX:
        raise ValueError(f"Cost {value!r} exceeds uint256 in micro-USDC")
    return micro_int


def normalize_attestation_hash(value: str) -> str:
    """Normalize an attestation hash to 64 lowercase hex characters.

    Accepts either a bare 64-hex string or a ``sha256:<64-hex>`` prefixed form.
    Raises :class:`ValueError` for any other shape so callers cannot smuggle
    truncated or mixed-case hashes into the event.
    """
    if not isinstance(value, str):
        raise TypeError(f"Attestation hash must be a string, got {type(value).__name__}")
    candidate = value.strip().lower()
    if candidate.startswith("sha256:"):
        candidate = candidate[len("sha256:") :]
    if not _HEX64_RE.match(candidate):
        raise ValueError(
            "Attestation hash must be a 64-character lowercase hex string "
            "(optionally prefixed with 'sha256:')."
        )
    return candidate


def normalize_model_id_uint(value: int | str) -> str:
    """Validate and normalize *value* as a ``uint256``-as-decimal-string."""
    if isinstance(value, bool):
        raise TypeError("model_id_uint cannot be a boolean")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"model_id_uint must be >= 0, got {value!r}")
        candidate = str(value)
    elif isinstance(value, str):
        candidate = value.strip()
        if not _DECIMAL_UINT_RE.match(candidate):
            raise ValueError(
                f"model_id_uint must be decimal digits with no leading zeros, got {value!r}"
            )
    else:
        raise TypeError(f"model_id_uint must be int or str, got {type(value).__name__}")

    as_int = int(candidate)
    if as_int > UINT256_MAX:
        raise ValueError(f"model_id_uint {value!r} exceeds uint256")
    return candidate


def make_idempotency_key(
    model_id_uint: int | str,
    eval_id: str,
    attestation_hash: str,
) -> str:
    """Build the canonical idempotency key for a DeltaOne acceptance event.

    Hash input is the exact UTF-8 string ``"{model_id_uint}:{eval_id}:{hash}"``
    after normalizing the model id (decimal string) and attestation hash
    (64 lowercase hex chars, no ``sha256:`` prefix).  Keep this formula in sync
    with ``hokusai-token`` ``DeltaVerifier`` if it ever recomputes the key.
    """
    model_decimal = normalize_model_id_uint(model_id_uint)
    if not isinstance(eval_id, str) or not eval_id:
        raise ValueError("eval_id must be a non-empty string")
    canonical_hash = normalize_attestation_hash(attestation_hash)
    payload = f"{model_decimal}:{eval_id}:{canonical_hash}"
    return sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class DeltaOneGuardrailBreachEvent(BaseModel):
    """Per-guardrail breach detail included in the audit summary block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_name: str = Field(..., min_length=1)
    observed: float
    threshold: float
    direction: Literal["higher_is_better", "lower_is_better"]
    policy: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class DeltaOneGuardrailSummary(BaseModel):
    """Aggregate guardrail outcome attached to a DeltaOne acceptance event.

    ``total_guardrails`` is the count configured in the benchmark spec; only
    blocking guardrails contribute breaches, but the count remains stable so
    downstream consumers can detect spec changes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_guardrails: int = Field(..., ge=0)
    guardrails_passed: int = Field(..., ge=0)
    breaches: tuple[DeltaOneGuardrailBreachEvent, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_counts(self: DeltaOneGuardrailSummary) -> DeltaOneGuardrailSummary:
        if self.guardrails_passed > self.total_guardrails:
            raise ValueError(
                f"guardrails_passed ({self.guardrails_passed}) must not exceed "
                f"total_guardrails ({self.total_guardrails})"
            )
        return self


class DeltaOneAcceptanceEvent(BaseModel):
    """Versioned event payload for an accepted DeltaOne mint."""

    model_config = ConfigDict(extra="forbid")

    event_version: Literal["deltaone.acceptance/v1"] = DELTAONE_ACCEPTANCE_EVENT_VERSION

    model_id: str = Field(..., min_length=1)
    model_id_uint: str = Field(
        ...,
        description="uint256-as-decimal-string for on-chain consumption",
    )

    eval_id: str = Field(..., min_length=1)
    mlflow_run_id: str = Field(..., min_length=1)
    benchmark_spec_id: str = Field(..., min_length=1)

    primary_metric_name: str = Field(..., min_length=1)
    primary_metric_mlflow_name: str = Field(..., min_length=1)
    metric_family: str = Field(..., min_length=1)

    baseline_score_bps: int = Field(..., ge=0, le=BPS_MAX)
    candidate_score_bps: int = Field(..., ge=0, le=BPS_MAX)
    delta_bps: int = Field(..., ge=-BPS_MAX, le=BPS_MAX)
    delta_threshold_bps: int = Field(..., ge=0, le=BPS_MAX)

    attestation_hash: str = Field(..., min_length=64, max_length=64)
    idempotency_key: str = Field(..., min_length=64, max_length=64)

    guardrails: DeltaOneGuardrailSummary

    max_cost_usd_micro: int = Field(..., ge=0, le=UINT256_MAX)
    actual_cost_usd_micro: int = Field(..., ge=0, le=UINT256_MAX)

    evaluated_at: str = Field(..., min_length=1, description="ISO-8601 UTC timestamp")

    @model_validator(mode="after")
    def _validate_invariants(self: DeltaOneAcceptanceEvent) -> DeltaOneAcceptanceEvent:
        if not _HEX64_RE.match(self.attestation_hash):
            raise ValueError("attestation_hash must be 64 lowercase hex chars")
        if not _HEX64_RE.match(self.idempotency_key):
            raise ValueError("idempotency_key must be 64 lowercase hex chars")
        if not _DECIMAL_UINT_RE.match(self.model_id_uint):
            raise ValueError("model_id_uint must be a non-negative decimal string")
        if int(self.model_id_uint) > UINT256_MAX:
            raise ValueError("model_id_uint exceeds uint256")
        if self.metric_family not in COMPARATOR_REGISTRY:
            raise ValueError(
                f"metric_family {self.metric_family!r} not in registry "
                f"({sorted(COMPARATOR_REGISTRY.keys())})"
            )
        if self.delta_bps != self.candidate_score_bps - self.baseline_score_bps:
            raise ValueError("delta_bps must equal candidate_score_bps - baseline_score_bps")
        return self


# JSON Schema is generated once at import time so downstream consumers can
# import it without re-deriving it on every call.
DELTAONE_ACCEPTANCE_EVENT_JSON_SCHEMA: dict[str, Any] = DeltaOneAcceptanceEvent.model_json_schema()


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeltaOneEventInputs:
    """Resolved inputs used to construct a :class:`DeltaOneAcceptanceEvent`.

    All fields are pre-resolved before reaching the builder so the builder is
    purely deterministic and easy to test.
    """

    model_id: str
    model_id_uint: int | str
    eval_id: str
    mlflow_run_id: str
    benchmark_spec_id: str
    primary_metric_name: str
    primary_metric_mlflow_name: str
    metric_family: str
    baseline_score: float
    candidate_score: float
    delta_threshold: float
    attestation_hash: str
    guardrail_total: int
    guardrail_result: GuardrailResult
    max_cost_usd: float | int | Decimal | str
    actual_cost_usd: float | int | Decimal | str
    evaluated_at: str


def _breach_to_event(breach: GuardrailBreach) -> DeltaOneGuardrailBreachEvent:
    return DeltaOneGuardrailBreachEvent(
        metric_name=breach.metric_name,
        observed=float(breach.observed),
        threshold=float(breach.threshold),
        direction=breach.direction,  # type: ignore[arg-type]
        policy=breach.policy,
        reason=breach.reason,
    )


def build_deltaone_acceptance_event(
    inputs: DeltaOneEventInputs,
) -> DeltaOneAcceptanceEvent:
    """Construct a validated :class:`DeltaOneAcceptanceEvent` from resolved inputs."""
    baseline_bps = to_basis_points(inputs.baseline_score, inputs.metric_family)
    candidate_bps = to_basis_points(inputs.candidate_score, inputs.metric_family)
    threshold_bps = to_basis_points(inputs.delta_threshold, inputs.metric_family)
    delta_bps = candidate_bps - baseline_bps

    canonical_hash = normalize_attestation_hash(inputs.attestation_hash)
    model_id_uint = normalize_model_id_uint(inputs.model_id_uint)
    idempotency_key = make_idempotency_key(model_id_uint, inputs.eval_id, canonical_hash)

    breaches = tuple(_breach_to_event(b) for b in inputs.guardrail_result.breaches)
    guardrails_passed = max(0, inputs.guardrail_total - len(breaches))
    summary = DeltaOneGuardrailSummary(
        total_guardrails=inputs.guardrail_total,
        guardrails_passed=guardrails_passed,
        breaches=breaches,
    )

    # primary metric mlflow name normalization: prefer the explicit value, but
    # if a caller passes the canonical Hokusai name, derive the MLflow key.
    mlflow_name = inputs.primary_metric_mlflow_name or derive_mlflow_name(
        inputs.primary_metric_name
    )

    return DeltaOneAcceptanceEvent(
        event_version=DELTAONE_ACCEPTANCE_EVENT_VERSION,
        model_id=inputs.model_id,
        model_id_uint=model_id_uint,
        eval_id=inputs.eval_id,
        mlflow_run_id=inputs.mlflow_run_id,
        benchmark_spec_id=inputs.benchmark_spec_id,
        primary_metric_name=inputs.primary_metric_name,
        primary_metric_mlflow_name=mlflow_name,
        metric_family=inputs.metric_family,
        baseline_score_bps=baseline_bps,
        candidate_score_bps=candidate_bps,
        delta_bps=delta_bps,
        delta_threshold_bps=threshold_bps,
        attestation_hash=canonical_hash,
        idempotency_key=idempotency_key,
        guardrails=summary,
        max_cost_usd_micro=to_micro_usdc(inputs.max_cost_usd),
        actual_cost_usd_micro=to_micro_usdc(inputs.actual_cost_usd),
        evaluated_at=inputs.evaluated_at,
    )
