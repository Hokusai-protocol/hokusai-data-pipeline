"""DeltaOne acceptance event schema and conversion helpers for on-chain DeltaVerifier.

Contract version: deltaone.acceptance/v1

This module defines the canonical event produced by DeltaOneMintOrchestrator before
publishing to Redis (HOK-1276) and consumed by the on-chain DeltaVerifier.  All
numeric quantities are normalized for unambiguous on-chain consumption:

- Scores and deltas: basis points (uint, 0-10000), ROUND_HALF_EVEN.
- Costs: USDC micro-units (uint, 6 decimals), ROUND_HALF_EVEN.
- Hashes: lowercase hex, 0x-prefixed, 64 hex digits (SHA-256).
- model_id_uint: uint256 as decimal string.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DELTAONE_ACCEPTANCE_EVENT_VERSION = "deltaone.acceptance/v1"

UINT256_MAX = 2**256 - 1

#: Supported metric families for v1 bps mapping.
SUPPORTED_METRIC_FAMILIES = frozenset(
    {
        "proportion",
        "continuous",
        "zero_inflated_continuous",
        "rank_or_ordinal",
    }
)

_HEX64_RE_LOWER = "0x" + "[0-9a-f]{64}"
_BPS_SCALE = Decimal("10000")
_MICRO_USDC_SCALE = Decimal("1000000")

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EventPayloadError(ValueError):
    """Raised when event payload construction fails with a typed reason."""

    def __init__(self: EventPayloadError, field: str, reason: str) -> None:
        self.field = field
        super().__init__(f"event_payload: {field}: {reason}")


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def to_basis_points(value: float, family: str) -> int:
    """Convert a metric value to basis points (0-10000) for the given metric family.

    For 'proportion': value must be in [0, 1]; scaled by 10000.
    For all other supported families: treated as a normalized value in [0, 1]
        for v1 (per-observation data is not available in aggregate HEM records).
        Values outside [0, 1] are clamped and documented as a v1 limitation.

    Rounding: ROUND_HALF_EVEN throughout. No Python round() is used.

    Raises
    ------
        EventPayloadError: for NaN, infinity, negative values, unsupported family,
            or proportion values outside [0, 1].

    """
    if family not in SUPPORTED_METRIC_FAMILIES:
        raise EventPayloadError(
            "metric_family",
            f"unsupported metric family {family!r}; supported: {sorted(SUPPORTED_METRIC_FAMILIES)}",
        )
    if math.isnan(value):
        raise EventPayloadError("value", "NaN is not a valid metric value for bps conversion")
    if math.isinf(value):
        raise EventPayloadError("value", "infinite value is not valid for bps conversion")
    if value < 0.0:
        raise EventPayloadError("value", f"negative metric value {value!r} is not valid")

    if family == "proportion":
        if value > 1.0:
            raise EventPayloadError(
                "value",
                f"proportion value {value!r} is outside [0, 1]; proportion metrics must be rates",
            )
        return int((Decimal(str(value)) * _BPS_SCALE).to_integral_value(rounding=ROUND_HALF_EVEN))

    # For non-proportion families in v1, clamp to [0, 1] if above 1 and document.
    # Callers providing pre-normalized values (e.g., NDCG, rank correlation) should
    # ensure they pass values in [0, 1]; values >1 are clamped to 10000 bps.
    clamped = min(value, 1.0)
    return int((Decimal(str(clamped)) * _BPS_SCALE).to_integral_value(rounding=ROUND_HALF_EVEN))


def to_micro_usdc(value: Decimal | float | None) -> int:
    """Convert a USD cost value to USDC micro-units (6 decimals), ROUND_HALF_EVEN.

    None maps to 0 (cost not available).
    Negative values and non-finite floats raise EventPayloadError.
    """
    if value is None:
        return 0
    d = _validate_and_coerce_cost(value)
    return int((d * _MICRO_USDC_SCALE).to_integral_value(rounding=ROUND_HALF_EVEN))


def _validate_and_coerce_cost(value: Decimal | float) -> Decimal:
    """Validate and coerce a cost value to Decimal; raise EventPayloadError on invalid input."""
    if isinstance(value, float):
        if math.isnan(value):
            raise EventPayloadError("cost", "NaN is not a valid cost value")
        if math.isinf(value):
            raise EventPayloadError("cost", "infinite value is not a valid cost value")
        if value < 0.0:
            raise EventPayloadError("cost", f"negative cost value {value!r} is not valid")
        return Decimal(str(value))
    if isinstance(value, Decimal):
        try:
            f = float(value)
        except (InvalidOperation, OverflowError) as exc:
            raise EventPayloadError(
                "cost", f"unrepresentable Decimal cost value {value!r}"
            ) from exc
        if math.isnan(f):
            raise EventPayloadError("cost", "NaN Decimal cost value is not valid")
        if math.isinf(f):
            raise EventPayloadError("cost", "infinite Decimal cost value is not valid")
        if value < 0:
            raise EventPayloadError("cost", f"negative Decimal cost value {value!r} is not valid")
        return value
    raise EventPayloadError("cost", f"unsupported cost value type {type(value).__name__!r}")


def make_idempotency_key(model_id_uint: int, eval_id: str, attestation_hash: str) -> str:
    """Compute canonical idempotency key as 0x-prefixed SHA-256.

    Input: '{model_id_uint}:{eval_id}:{attestation_hash_bare_hex}'.
    Accepts bare 64-hex or 0x-prefixed hash.
    Raises EventPayloadError for invalid model_id_uint, empty eval_id, or bad hash.
    """
    if not isinstance(model_id_uint, int) or model_id_uint < 0 or model_id_uint > UINT256_MAX:
        raise EventPayloadError(
            "model_id_uint", f"must be an integer in [0, 2^256 - 1]; got {model_id_uint!r}"
        )
    if not eval_id or not eval_id.strip():
        raise EventPayloadError("eval_id", "eval_id must be a non-empty string")
    norm_hash = _normalize_hash_input(attestation_hash, field="attestation_hash")
    raw = f"{model_id_uint}:{eval_id}:{norm_hash}"
    return "0x" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_sha256(payload: dict[str, Any]) -> str:
    """Compute SHA-256 over canonicalized JSON (sort_keys=True, compact, UTF-8).

    Returns lowercase 0x-prefixed 64-hex digest.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "0x" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_hash_input(value: str, *, field: str) -> str:
    """Accept bare 64-hex or 0x-prefixed SHA-256 hash; return normalized bare 64-hex."""
    if not isinstance(value, str):
        raise EventPayloadError(field, f"expected a string hash, got {type(value).__name__!r}")
    lower = value.lower()
    bare = lower[2:] if lower.startswith("0x") else lower
    if len(bare) != 64 or not all(c in "0123456789abcdef" for c in bare):
        raise EventPayloadError(
            field,
            f"expected a 64-hex SHA-256 hash (with or without 0x prefix), got {value!r}",
        )
    return bare


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class DeltaOneGuardrailBreach(BaseModel):
    """A single guardrail violation in the acceptance event."""

    model_config = ConfigDict(extra="forbid")

    metric_name: str = Field(..., min_length=1)
    observed_bps: int = Field(..., ge=0, le=10000)
    threshold_bps: int = Field(..., ge=0, le=10000)
    observed: float
    threshold: float
    direction: str = Field(..., pattern=r"^(higher_is_better|lower_is_better)$")
    policy: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class DeltaOneGuardrailSummary(BaseModel):
    """Aggregated guardrail evaluation result embedded in the acceptance event."""

    model_config = ConfigDict(extra="forbid")

    total_guardrails: int = Field(..., ge=0)
    guardrails_passed: int = Field(..., ge=0)
    breaches: list[DeltaOneGuardrailBreach] = Field(default_factory=list)

    @model_validator(mode="after")
    def _passed_lte_total(self: DeltaOneGuardrailSummary) -> DeltaOneGuardrailSummary:
        if self.guardrails_passed > self.total_guardrails:
            raise ValueError(
                f"guardrails_passed ({self.guardrails_passed}) cannot exceed "
                f"total_guardrails ({self.total_guardrails})"
            )
        return self


class DeltaOneAcceptanceEvent(BaseModel):
    """Versioned acceptance event emitted before DeltaOne mint for on-chain DeltaVerifier.

    All numeric scores are in basis points (0-10000).  Cost fields are in USDC
    micro-units (6 decimals).  All SHA-256 hashes are lowercase, 0x-prefixed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Event identity
    event_version: Literal["deltaone.acceptance/v1"] = DELTAONE_ACCEPTANCE_EVENT_VERSION

    # Model and eval references
    model_id: str = Field(..., min_length=1)
    model_id_uint: str = Field(
        ...,
        description="uint256 as decimal string for on-chain consumption",
    )
    eval_id: str = Field(..., min_length=1)
    mlflow_run_id: str = Field(..., min_length=1)
    benchmark_spec_id: str = Field(..., min_length=1)

    # Primary metric
    primary_metric_name: str = Field(..., min_length=1)
    primary_metric_mlflow_name: str = Field(..., min_length=1)
    metric_family: str = Field(..., min_length=1)

    # Scores in basis points
    baseline_score_bps: int = Field(..., ge=0, le=10000)
    candidate_score_bps: int = Field(..., ge=0, le=10000)
    delta_bps: int = Field(..., ge=0, le=10000)
    delta_threshold_bps: int = Field(..., ge=0, le=10000)

    # Cryptographic anchors
    attestation_hash: str = Field(..., description="SHA-256 of canonical HEM payload, 0x-prefixed")
    idempotency_key: str = Field(
        ..., description="SHA-256 of model_id_uint:eval_id:attestation_hash, 0x-prefixed"
    )

    # Guardrail summary
    guardrail_summary: DeltaOneGuardrailSummary

    # Cost fields (USDC micro-units, 6 decimals)
    max_cost_usd_micro: int = Field(..., ge=0)
    actual_cost_usd_micro: int = Field(..., ge=0)

    @field_validator("model_id_uint")
    @classmethod
    def _validate_model_id_uint(cls: type, v: str) -> str:
        try:
            n = int(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"model_id_uint must be a decimal integer string, got {v!r}") from exc
        if n < 0 or n > UINT256_MAX:
            raise ValueError(f"model_id_uint {v!r} is outside uint256 range [0, 2^256-1]")
        return v

    @field_validator("attestation_hash", "idempotency_key")
    @classmethod
    def _validate_0x_sha256(cls: type, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError(f"hash field must be a string, got {type(v).__name__!r}")
        lower = v.lower()
        if not lower.startswith("0x"):
            raise ValueError(f"hash must be 0x-prefixed, got {v!r}")
        bare = lower[2:]
        if len(bare) != 64 or not all(c in "0123456789abcdef" for c in bare):
            raise ValueError(f"expected 0x-prefixed 64-hex SHA-256, got {v!r}")
        return v.lower()

    @field_validator("metric_family")
    @classmethod
    def _validate_metric_family(cls: type, v: str) -> str:
        if v not in SUPPORTED_METRIC_FAMILIES:
            raise ValueError(
                f"metric_family {v!r} is not supported; "
                f"supported: {sorted(SUPPORTED_METRIC_FAMILIES)}"
            )
        return v

    @model_validator(mode="after")
    def _validate_delta_consistency(self: DeltaOneAcceptanceEvent) -> DeltaOneAcceptanceEvent:
        expected_delta = self.candidate_score_bps - self.baseline_score_bps
        if self.delta_bps != expected_delta:
            raise ValueError(
                f"delta_bps ({self.delta_bps}) must equal "
                f"candidate_score_bps - baseline_score_bps "
                f"({self.candidate_score_bps} - {self.baseline_score_bps} = {expected_delta})"
            )
        return self
