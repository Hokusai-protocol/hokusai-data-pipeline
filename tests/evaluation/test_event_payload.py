"""Unit tests for the DeltaOne acceptance event schema and conversion helpers."""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from src.evaluation.event_payload import (
    BPS_MAX,
    DELTAONE_ACCEPTANCE_EVENT_JSON_SCHEMA,
    DELTAONE_ACCEPTANCE_EVENT_VERSION,
    UINT256_MAX,
    DeltaOneAcceptanceEvent,
    DeltaOneEventInputs,
    DeltaOneGuardrailSummary,
    build_deltaone_acceptance_event,
    make_idempotency_key,
    normalize_attestation_hash,
    normalize_model_id_uint,
    to_basis_points,
    to_micro_usdc,
)
from src.evaluation.schema import GuardrailBreach, GuardrailResult

HASH_HEX = "a" * 64


# ---------------------------------------------------------------------------
# to_basis_points
# ---------------------------------------------------------------------------


class TestToBasisPoints:
    def test_lower_bound(self):
        assert to_basis_points(0.0, "proportion") == 0

    def test_upper_bound(self):
        assert to_basis_points(1.0, "proportion") == BPS_MAX

    def test_half_up_rounding_banker_avoidance(self):
        # 0.12345 * 10000 = 1234.5 -> 1235 under HALF_UP (not banker's rounding).
        assert to_basis_points(0.12345, "proportion") == 1235

    def test_decimal_string_input(self):
        assert to_basis_points("0.5", "proportion") == 5000

    def test_decimal_input(self):
        assert to_basis_points(Decimal("0.42"), "proportion") == 4200

    def test_int_input(self):
        assert to_basis_points(1, "proportion") == BPS_MAX
        assert to_basis_points(0, "proportion") == 0

    def test_continuous_family(self):
        assert to_basis_points(0.5, "continuous") == 5000

    def test_zero_inflated_family(self):
        assert to_basis_points(0.5, "zero_inflated_continuous") == 5000

    def test_rank_or_ordinal_family(self):
        assert to_basis_points(0.5, "rank_or_ordinal") == 5000

    def test_unknown_family_rejected(self):
        with pytest.raises(ValueError, match="Unknown metric_family"):
            to_basis_points(0.5, "fictional_family")

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            to_basis_points(float("nan"), "proportion")

    def test_inf_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            to_basis_points(float("inf"), "proportion")
        with pytest.raises(ValueError, match="finite"):
            to_basis_points(-math.inf, "proportion")

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match=">= 0"):
            to_basis_points(-0.01, "proportion")

    def test_above_one_rejected(self):
        with pytest.raises(ValueError, match="<= 1.0"):
            to_basis_points(1.0001, "proportion")

    def test_bool_rejected(self):
        with pytest.raises(TypeError):
            to_basis_points(True, "proportion")

    def test_garbage_string_rejected(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            to_basis_points("not-a-number", "proportion")


# ---------------------------------------------------------------------------
# to_micro_usdc
# ---------------------------------------------------------------------------


class TestToMicroUsdc:
    def test_basic_conversion(self):
        assert to_micro_usdc(Decimal("2.50")) == 2_500_000

    def test_zero(self):
        assert to_micro_usdc(0) == 0

    def test_float_avoids_binary_artifacts(self):
        # 0.1 + 0.2 in float is 0.30000000000000004; we accept the float
        # but convert via Decimal(str(value)) so 0.3 -> 300000.
        assert to_micro_usdc(0.3) == 300_000

    def test_string_input(self):
        assert to_micro_usdc("12.345678") == 12_345_678

    def test_half_up_rounding(self):
        # 0.0000005 * 1e6 = 0.5 -> rounds to 1 under HALF_UP.
        assert to_micro_usdc("0.0000005") == 1

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match=">= 0"):
            to_micro_usdc(-1.0)

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            to_micro_usdc(float("nan"))

    def test_inf_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            to_micro_usdc(float("inf"))

    def test_uint256_overflow_rejected(self):
        # value * 1e6 > uint256 max
        massive = Decimal(UINT256_MAX) + 1
        with pytest.raises(ValueError, match="exceeds uint256"):
            to_micro_usdc(massive)


# ---------------------------------------------------------------------------
# normalize helpers
# ---------------------------------------------------------------------------


class TestNormalizeAttestationHash:
    def test_bare_hex(self):
        assert normalize_attestation_hash(HASH_HEX) == HASH_HEX

    def test_sha256_prefix_stripped(self):
        assert normalize_attestation_hash("sha256:" + HASH_HEX) == HASH_HEX

    def test_uppercase_lowered(self):
        assert normalize_attestation_hash("A" * 64) == HASH_HEX

    def test_whitespace_trimmed(self):
        assert normalize_attestation_hash("  " + HASH_HEX + "\n") == HASH_HEX

    def test_short_rejected(self):
        with pytest.raises(ValueError):
            normalize_attestation_hash("a" * 63)

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError):
            normalize_attestation_hash("g" * 64)

    def test_non_string_rejected(self):
        with pytest.raises(TypeError):
            normalize_attestation_hash(123)  # type: ignore[arg-type]


class TestNormalizeModelIdUint:
    def test_int(self):
        assert normalize_model_id_uint(42) == "42"

    def test_zero(self):
        assert normalize_model_id_uint(0) == "0"

    def test_string(self):
        assert normalize_model_id_uint("42") == "42"

    def test_negative_int_rejected(self):
        with pytest.raises(ValueError):
            normalize_model_id_uint(-1)

    def test_leading_zero_rejected(self):
        with pytest.raises(ValueError):
            normalize_model_id_uint("042")

    def test_bool_rejected(self):
        with pytest.raises(TypeError):
            normalize_model_id_uint(True)  # type: ignore[arg-type]

    def test_overflow_rejected(self):
        with pytest.raises(ValueError):
            normalize_model_id_uint(UINT256_MAX + 1)


class TestMakeIdempotencyKey:
    def test_known_value(self):
        # Hand-computed: sha256("42:eval-1:" + "a"*64)
        expected = hashlib.sha256(b"42:eval-1:" + b"a" * 64).hexdigest()
        assert make_idempotency_key(42, "eval-1", HASH_HEX) == expected

    def test_accepts_string_model_id(self):
        assert make_idempotency_key("42", "eval-1", HASH_HEX) == make_idempotency_key(
            42, "eval-1", HASH_HEX
        )

    def test_strips_sha256_prefix(self):
        with_prefix = make_idempotency_key(42, "eval-1", "sha256:" + HASH_HEX)
        bare = make_idempotency_key(42, "eval-1", HASH_HEX)
        assert with_prefix == bare

    def test_empty_eval_id_rejected(self):
        with pytest.raises(ValueError):
            make_idempotency_key(42, "", HASH_HEX)

    def test_invalid_hash_rejected(self):
        with pytest.raises(ValueError):
            make_idempotency_key(42, "eval-1", "nope")


# ---------------------------------------------------------------------------
# Pydantic + JSON Schema round trip
# ---------------------------------------------------------------------------


def _good_event_kwargs() -> dict:
    return {
        "event_version": DELTAONE_ACCEPTANCE_EVENT_VERSION,
        "model_id": "model-x",
        "model_id_uint": "42",
        "eval_id": "eval-1",
        "mlflow_run_id": "run-cand",
        "benchmark_spec_id": "spec-1",
        "primary_metric_name": "accuracy",
        "primary_metric_mlflow_name": "accuracy",
        "metric_family": "proportion",
        "baseline_score_bps": 8000,
        "candidate_score_bps": 8500,
        "delta_bps": 500,
        "delta_threshold_bps": 100,
        "attestation_hash": HASH_HEX,
        "idempotency_key": "b" * 64,
        "guardrails": {
            "total_guardrails": 1,
            "guardrails_passed": 1,
            "breaches": [],
        },
        "max_cost_usd_micro": 1_000_000,
        "actual_cost_usd_micro": 800_000,
        "evaluated_at": "2026-05-04T00:00:00Z",
    }


class TestDeltaOneAcceptanceEvent:
    def test_round_trip_valid(self):
        event = DeltaOneAcceptanceEvent(**_good_event_kwargs())
        assert event.event_version == DELTAONE_ACCEPTANCE_EVENT_VERSION
        # JSON dump should be plain primitives.
        dumped = event.model_dump(mode="json")
        assert dumped["model_id_uint"] == "42"
        assert dumped["candidate_score_bps"] == 8500
        # Re-parse to confirm round trip.
        DeltaOneAcceptanceEvent(**dumped)

    def test_bad_event_version(self):
        kwargs = _good_event_kwargs()
        kwargs["event_version"] = "deltaone.acceptance/v0"
        with pytest.raises(ValidationError):
            DeltaOneAcceptanceEvent(**kwargs)

    def test_invalid_uint_string(self):
        kwargs = _good_event_kwargs()
        kwargs["model_id_uint"] = "0x1f"
        with pytest.raises(ValidationError):
            DeltaOneAcceptanceEvent(**kwargs)

    def test_bps_above_max(self):
        kwargs = _good_event_kwargs()
        kwargs["candidate_score_bps"] = BPS_MAX + 1
        with pytest.raises(ValidationError):
            DeltaOneAcceptanceEvent(**kwargs)

    def test_bps_below_zero(self):
        kwargs = _good_event_kwargs()
        kwargs["baseline_score_bps"] = -1
        with pytest.raises(ValidationError):
            DeltaOneAcceptanceEvent(**kwargs)

    def test_attestation_hash_non_hex(self):
        kwargs = _good_event_kwargs()
        kwargs["attestation_hash"] = "g" * 64
        with pytest.raises(ValidationError):
            DeltaOneAcceptanceEvent(**kwargs)

    def test_attestation_hash_uppercase(self):
        kwargs = _good_event_kwargs()
        kwargs["attestation_hash"] = "A" * 64
        with pytest.raises(ValidationError):
            DeltaOneAcceptanceEvent(**kwargs)

    def test_delta_bps_must_match(self):
        kwargs = _good_event_kwargs()
        kwargs["delta_bps"] = 999  # candidate - baseline = 500, mismatch
        with pytest.raises(ValidationError):
            DeltaOneAcceptanceEvent(**kwargs)

    def test_extra_fields_forbidden(self):
        kwargs = _good_event_kwargs()
        kwargs["surprise"] = "value"
        with pytest.raises(ValidationError):
            DeltaOneAcceptanceEvent(**kwargs)

    def test_unknown_metric_family(self):
        kwargs = _good_event_kwargs()
        kwargs["metric_family"] = "bogus"
        with pytest.raises(ValidationError):
            DeltaOneAcceptanceEvent(**kwargs)


class TestGuardrailSummary:
    def test_valid(self):
        summary = DeltaOneGuardrailSummary(total_guardrails=2, guardrails_passed=2, breaches=())
        assert summary.guardrails_passed == 2

    def test_passed_exceeds_total(self):
        with pytest.raises(ValidationError):
            DeltaOneGuardrailSummary(total_guardrails=1, guardrails_passed=2, breaches=())


class TestJsonSchemaValidation:
    def test_round_trip_via_jsonschema(self):
        event = DeltaOneAcceptanceEvent(**_good_event_kwargs())
        validator = Draft202012Validator(DELTAONE_ACCEPTANCE_EVENT_JSON_SCHEMA)
        errors = list(validator.iter_errors(event.model_dump(mode="json")))
        assert errors == []

    def test_on_disk_schema_matches_pydantic(self):
        """The committed schema artifact must match the Pydantic-derived schema."""
        from pathlib import Path

        artifact = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "schemas"
            / "deltaone_acceptance_event_v1.schema.json"
        )
        on_disk = json.loads(artifact.read_text())
        # Compare canonical forms so dict ordering does not cause spurious diffs.
        on_disk_canonical = json.dumps(on_disk, sort_keys=True)
        live_canonical = json.dumps(DELTAONE_ACCEPTANCE_EVENT_JSON_SCHEMA, sort_keys=True)
        assert on_disk_canonical == live_canonical, (
            "docs/schemas/deltaone_acceptance_event_v1.schema.json is "
            "out of sync with the Pydantic model"
        )

    def test_jsonschema_rejects_missing_fields(self):
        partial = _good_event_kwargs()
        partial.pop("idempotency_key")
        validator = Draft202012Validator(DELTAONE_ACCEPTANCE_EVENT_JSON_SCHEMA)
        errors = list(validator.iter_errors(partial))
        assert errors

    def test_jsonschema_rejects_out_of_range_bps(self):
        bad = _good_event_kwargs()
        bad["candidate_score_bps"] = 11000
        validator = Draft202012Validator(DELTAONE_ACCEPTANCE_EVENT_JSON_SCHEMA)
        errors = list(validator.iter_errors(bad))
        assert errors


# ---------------------------------------------------------------------------
# build_deltaone_acceptance_event
# ---------------------------------------------------------------------------


def _good_inputs(**overrides) -> DeltaOneEventInputs:
    base = {
        "model_id": "model-x",
        "model_id_uint": 42,
        "eval_id": "eval-1",
        "mlflow_run_id": "run-cand",
        "benchmark_spec_id": "spec-1",
        "primary_metric_name": "accuracy",
        "primary_metric_mlflow_name": "accuracy",
        "metric_family": "proportion",
        "baseline_score": 0.80,
        "candidate_score": 0.85,
        "delta_threshold": 0.01,
        "attestation_hash": HASH_HEX,
        "guardrail_total": 2,
        "guardrail_result": GuardrailResult(passed=True, breaches=()),
        "max_cost_usd": 1.0,
        "actual_cost_usd": 0.5,
        "evaluated_at": "2026-05-04T00:00:00Z",
    }
    base.update(overrides)
    return DeltaOneEventInputs(**base)


class TestBuilder:
    def test_happy_path(self):
        event = build_deltaone_acceptance_event(_good_inputs())
        assert event.candidate_score_bps == 8500
        assert event.baseline_score_bps == 8000
        assert event.delta_bps == 500
        assert event.delta_threshold_bps == 100
        assert event.idempotency_key == make_idempotency_key(42, "eval-1", HASH_HEX)
        assert event.guardrails.total_guardrails == 2
        assert event.guardrails.guardrails_passed == 2
        assert event.max_cost_usd_micro == 1_000_000
        assert event.actual_cost_usd_micro == 500_000

    def test_breach_decrements_passed(self):
        breach = GuardrailBreach(
            metric_name="cost_per_call",
            observed=0.5,
            threshold=0.1,
            direction="lower_is_better",
            policy="reject_mint",
            reason="cost exceeds threshold",
        )
        event = build_deltaone_acceptance_event(
            _good_inputs(
                guardrail_total=2,
                guardrail_result=GuardrailResult(passed=False, breaches=(breach,)),
            )
        )
        assert event.guardrails.guardrails_passed == 1
        assert event.guardrails.breaches[0].metric_name == "cost_per_call"

    def test_normalizes_sha256_prefix(self):
        event = build_deltaone_acceptance_event(_good_inputs(attestation_hash="sha256:" + HASH_HEX))
        assert event.attestation_hash == HASH_HEX

    def test_derives_mlflow_name_when_blank(self):
        event = build_deltaone_acceptance_event(
            _good_inputs(
                primary_metric_name="custom:my_metric",
                primary_metric_mlflow_name="",
            )
        )
        assert event.primary_metric_mlflow_name == "custom_my_metric"

    def test_zero_costs(self):
        event = build_deltaone_acceptance_event(_good_inputs(max_cost_usd=0, actual_cost_usd=0))
        assert event.max_cost_usd_micro == 0
        assert event.actual_cost_usd_micro == 0
