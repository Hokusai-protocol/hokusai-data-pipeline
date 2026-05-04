"""Unit tests for src/evaluation/event_payload.py.

Tests cover:
- to_basis_points(): all edge cases (0.0, 1.0, NaN, inf, negative, >1, families)
- to_micro_usdc(): None, zero, Decimal, half-even ties, negative, NaN, inf
- make_idempotency_key(): valid formula, invalid model ids, empty eval_id, bad hashes
- DeltaOneAcceptanceEvent: Pydantic field validation, extra-forbid, v1 literal
- JSON Schema drift test against schema/deltaone_acceptance_event.v1.json
- Fixture validation: example fixture round-trips through Pydantic and JSON Schema
- Deterministic JSON bytes for identical inputs
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.evaluation.event_payload import (
    DELTAONE_ACCEPTANCE_EVENT_VERSION,
    SUPPORTED_METRIC_FAMILIES,
    UINT256_MAX,
    DeltaOneAcceptanceEvent,
    DeltaOneGuardrailBreach,
    DeltaOneGuardrailSummary,
    EventPayloadError,
    canonical_sha256,
    make_idempotency_key,
    to_basis_points,
    to_micro_usdc,
)

REPO_ROOT = Path(__file__).parents[2]
SCHEMA_FILE = REPO_ROOT / "schema" / "deltaone_acceptance_event.v1.json"
EXAMPLE_FILE = REPO_ROOT / "schema" / "examples" / "deltaone_acceptance_event.v1.json"


# ---------------------------------------------------------------------------
# Helpers to build a valid event
# ---------------------------------------------------------------------------


def _valid_event(**overrides: object) -> DeltaOneAcceptanceEvent:
    att_hash = "0x" + "a" * 64
    idempotency_key = "0x" + "b" * 64
    defaults: dict[str, object] = {
        "model_id": "model-a",
        "model_id_uint": "12345",
        "eval_id": "eval-001",
        "mlflow_run_id": "run-abc",
        "benchmark_spec_id": "spec-v1",
        "primary_metric_name": "accuracy",
        "primary_metric_mlflow_name": "accuracy",
        "metric_family": "proportion",
        "baseline_score_bps": 7800,
        "candidate_score_bps": 8100,
        "delta_bps": 300,
        "delta_threshold_bps": 100,
        "attestation_hash": att_hash,
        "idempotency_key": idempotency_key,
        "guardrail_summary": DeltaOneGuardrailSummary(
            total_guardrails=0, guardrails_passed=0, breaches=[]
        ),
        "max_cost_usd_micro": 5_000_000,
        "actual_cost_usd_micro": 2_340_000,
    }
    defaults.update(overrides)
    return DeltaOneAcceptanceEvent(**defaults)


# ---------------------------------------------------------------------------
# to_basis_points
# ---------------------------------------------------------------------------


class TestToBasisPoints:
    def test_zero_proportion(self) -> None:
        assert to_basis_points(0.0, "proportion") == 0

    def test_one_proportion(self) -> None:
        assert to_basis_points(1.0, "proportion") == 10000

    def test_half_proportion(self) -> None:
        assert to_basis_points(0.5, "proportion") == 5000

    def test_round_half_even_ties(self) -> None:
        # 0.00005 * 10000 = 0.5 -> rounds to 0 (half-even)
        assert to_basis_points(0.00005, "proportion") == 0
        # 0.00015 * 10000 = 1.5 -> rounds to 2 (half-even)
        assert to_basis_points(0.00015, "proportion") == 2

    def test_typical_proportion(self) -> None:
        result = to_basis_points(0.12345, "proportion")
        # 0.12345 * 10000 = 1234.5 -> half-even rounds to 1234 (nearest even)
        from decimal import ROUND_HALF_EVEN, Decimal

        expected = int(
            (Decimal("0.12345") * Decimal("10000")).to_integral_value(rounding=ROUND_HALF_EVEN)
        )
        assert result == expected
        assert result == 1234

    def test_nan_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="NaN"):
            to_basis_points(float("nan"), "proportion")

    def test_inf_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="infinite"):
            to_basis_points(float("inf"), "proportion")

    def test_negative_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="negative"):
            to_basis_points(-0.1, "proportion")

    def test_proportion_above_one_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="outside \\[0, 1\\]"):
            to_basis_points(1.001, "proportion")

    def test_unsupported_family_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="unsupported metric family"):
            to_basis_points(0.5, "unknown_family")

    def test_continuous_family_valid(self) -> None:
        result = to_basis_points(0.75, "continuous")
        assert result == 7500

    def test_continuous_above_one_clamped(self) -> None:
        # Non-proportion families clamp values >1 to 10000 (documented v1 behavior)
        result = to_basis_points(1.5, "continuous")
        assert result == 10000

    def test_zero_inflated_continuous(self) -> None:
        assert to_basis_points(0.0, "zero_inflated_continuous") == 0

    def test_rank_or_ordinal(self) -> None:
        assert to_basis_points(0.5, "rank_or_ordinal") == 5000

    def test_all_supported_families_accepted(self) -> None:
        for family in SUPPORTED_METRIC_FAMILIES:
            result = to_basis_points(0.5, family)
            assert 0 <= result <= 10000


# ---------------------------------------------------------------------------
# to_micro_usdc
# ---------------------------------------------------------------------------


class TestToMicroUsdc:
    def test_none_maps_to_zero(self) -> None:
        assert to_micro_usdc(None) == 0

    def test_zero_float(self) -> None:
        assert to_micro_usdc(0.0) == 0

    def test_zero_decimal(self) -> None:
        assert to_micro_usdc(Decimal("0")) == 0

    def test_typical_decimal(self) -> None:
        assert to_micro_usdc(Decimal("1.234567")) == 1_234_567

    def test_typical_float(self) -> None:
        assert to_micro_usdc(2.34) == 2_340_000

    def test_half_even_rounding(self) -> None:
        # 1.0000005 * 1e6 = 1000000.5 -> half-even -> 1000000 (nearest even)
        assert to_micro_usdc(Decimal("1.0000005")) == 1_000_000
        # 0.0000015 * 1e6 = 1.5 -> half-even -> 2 (nearest even)
        assert to_micro_usdc(Decimal("0.0000015")) == 2

    def test_negative_float_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="negative"):
            to_micro_usdc(-1.0)

    def test_negative_decimal_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="negative"):
            to_micro_usdc(Decimal("-0.001"))

    def test_nan_float_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="NaN"):
            to_micro_usdc(float("nan"))

    def test_inf_float_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="infinite"):
            to_micro_usdc(float("inf"))

    def test_large_value(self) -> None:
        result = to_micro_usdc(1000.0)
        assert result == 1_000_000_000


# ---------------------------------------------------------------------------
# make_idempotency_key
# ---------------------------------------------------------------------------


class TestMakeIdempotencyKey:
    def test_valid_formula(self) -> None:
        import hashlib

        model_id_uint = 99999
        eval_id = "eval-abc"
        attestation_hash = "0x" + "f" * 64
        norm_hash = "f" * 64
        raw = f"{model_id_uint}:{eval_id}:{norm_hash}"
        expected = "0x" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
        result = make_idempotency_key(model_id_uint, eval_id, attestation_hash)
        assert result == expected

    def test_accepts_bare_hex_hash(self) -> None:
        bare_hash = "a" * 64
        prefixed_hash = "0x" + bare_hash
        result_bare = make_idempotency_key(1, "eval", bare_hash)
        result_prefixed = make_idempotency_key(1, "eval", prefixed_hash)
        assert result_bare == result_prefixed

    def test_uppercase_hash_normalized(self) -> None:
        lower_hash = "0x" + "a" * 64
        upper_hash = "0x" + "A" * 64
        result_lower = make_idempotency_key(1, "eval", lower_hash)
        result_upper = make_idempotency_key(1, "eval", upper_hash)
        assert result_lower == result_upper

    def test_result_is_0x_prefixed(self) -> None:
        result = make_idempotency_key(1, "eval", "0x" + "a" * 64)
        assert result.startswith("0x")
        assert len(result) == 66  # 0x + 64 hex

    def test_invalid_model_id_uint_negative(self) -> None:
        with pytest.raises(EventPayloadError, match="model_id_uint"):
            make_idempotency_key(-1, "eval", "0x" + "a" * 64)

    def test_invalid_model_id_uint_too_large(self) -> None:
        with pytest.raises(EventPayloadError, match="model_id_uint"):
            make_idempotency_key(UINT256_MAX + 1, "eval", "0x" + "a" * 64)

    def test_zero_model_id_uint_valid(self) -> None:
        result = make_idempotency_key(0, "eval", "0x" + "a" * 64)
        assert result.startswith("0x")

    def test_max_model_id_uint_valid(self) -> None:
        result = make_idempotency_key(UINT256_MAX, "eval", "0x" + "a" * 64)
        assert result.startswith("0x")

    def test_empty_eval_id_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="eval_id"):
            make_idempotency_key(1, "", "0x" + "a" * 64)

    def test_whitespace_eval_id_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="eval_id"):
            make_idempotency_key(1, "   ", "0x" + "a" * 64)

    def test_malformed_hash_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="attestation_hash"):
            make_idempotency_key(1, "eval", "not-a-hash")

    def test_wrong_length_hash_raises(self) -> None:
        with pytest.raises(EventPayloadError, match="attestation_hash"):
            make_idempotency_key(1, "eval", "0x" + "a" * 32)


# ---------------------------------------------------------------------------
# DeltaOneAcceptanceEvent model validation
# ---------------------------------------------------------------------------


class TestDeltaOneAcceptanceEvent:
    def test_valid_event_constructs(self) -> None:
        event = _valid_event()
        assert event.event_version == DELTAONE_ACCEPTANCE_EVENT_VERSION
        assert event.model_id == "model-a"

    def test_event_version_literal(self) -> None:
        event = _valid_event()
        assert event.event_version == "deltaone.acceptance/v1"

    def test_extra_fields_forbidden(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="extra_forbidden"):
            _valid_event(unknown_field="x")

    def test_model_id_uint_valid_decimal_string(self) -> None:
        event = _valid_event(model_id_uint=str(UINT256_MAX))
        assert event.model_id_uint == str(UINT256_MAX)

    def test_model_id_uint_must_be_decimal(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _valid_event(model_id_uint="0xdeadbeef")

    def test_model_id_uint_must_be_non_negative(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _valid_event(model_id_uint="-1")

    def test_attestation_hash_must_be_0x_prefixed(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _valid_event(attestation_hash="a" * 64)

    def test_attestation_hash_normalized_to_lowercase(self) -> None:
        event = _valid_event(attestation_hash="0x" + "A" * 64)
        assert event.attestation_hash == "0x" + "a" * 64

    def test_idempotency_key_must_be_0x_prefixed(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _valid_event(idempotency_key="b" * 64)

    def test_delta_bps_must_equal_candidate_minus_baseline(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="delta_bps"):
            _valid_event(baseline_score_bps=7800, candidate_score_bps=8100, delta_bps=999)

    def test_bps_fields_in_range(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _valid_event(baseline_score_bps=-1)
        with pytest.raises(ValidationError):
            # candidate > 10000 also invalid
            _valid_event(
                baseline_score_bps=9800,
                candidate_score_bps=10100,
                delta_bps=300,
            )

    def test_unsupported_metric_family_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="metric_family"):
            _valid_event(metric_family="unknown_family")

    def test_model_dump_is_serializable(self) -> None:
        event = _valid_event()
        data = event.model_dump()
        # Must round-trip through JSON
        json_str = json.dumps(data)
        reconstructed = DeltaOneAcceptanceEvent(**json.loads(json_str))
        assert reconstructed == event

    def test_guardrail_summary_passed_lte_total(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _valid_event(
                guardrail_summary=DeltaOneGuardrailSummary(
                    total_guardrails=1, guardrails_passed=2, breaches=[]
                )
            )

    def test_guardrail_breach_embedded(self) -> None:
        breach = DeltaOneGuardrailBreach(
            metric_name="toxicity",
            observed_bps=500,
            threshold_bps=200,
            observed=0.05,
            threshold=0.02,
            direction="lower_is_better",
            policy="reject_mint",
            reason="toxicity 0.05 exceeds threshold 0.02",
        )
        summary = DeltaOneGuardrailSummary(
            total_guardrails=1, guardrails_passed=0, breaches=[breach]
        )
        event = _valid_event(guardrail_summary=summary)
        assert len(event.guardrail_summary.breaches) == 1
        assert event.guardrail_summary.breaches[0].metric_name == "toxicity"


# ---------------------------------------------------------------------------
# JSON Schema drift test
# ---------------------------------------------------------------------------


class TestJsonSchemaDrift:
    def test_schema_file_matches_generated(self) -> None:
        """Regenerate schema and compare byte-for-byte to committed file."""
        if not SCHEMA_FILE.exists():
            pytest.skip(f"Schema file not found: {SCHEMA_FILE}")

        committed = json.loads(SCHEMA_FILE.read_text())
        generated = DeltaOneAcceptanceEvent.model_json_schema()

        committed_canonical = json.dumps(committed, sort_keys=True, indent=2)
        generated_canonical = json.dumps(generated, sort_keys=True, indent=2)

        assert (
            committed_canonical == generated_canonical
        ), f"Committed schema diverges from generated schema. Regenerate: {SCHEMA_FILE}"

    def test_example_fixture_validates_against_pydantic(self) -> None:
        """Golden fixture round-trips through Pydantic validation."""
        if not EXAMPLE_FILE.exists():
            pytest.skip(f"Example fixture not found: {EXAMPLE_FILE}")

        data = json.loads(EXAMPLE_FILE.read_text())
        event = DeltaOneAcceptanceEvent(**data)
        assert event.event_version == DELTAONE_ACCEPTANCE_EVENT_VERSION

    def test_example_fixture_validates_against_json_schema(self) -> None:
        """Golden fixture passes JSON Schema validation."""
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")

        if not SCHEMA_FILE.exists() or not EXAMPLE_FILE.exists():
            pytest.skip("Schema or example file not found")

        schema = json.loads(SCHEMA_FILE.read_text())
        instance = json.loads(EXAMPLE_FILE.read_text())
        jsonschema.validate(instance, schema)

    def test_example_fixture_field_by_field(self) -> None:
        """Verify every contract field is present in the example fixture."""
        if not EXAMPLE_FILE.exists():
            pytest.skip(f"Example fixture not found: {EXAMPLE_FILE}")

        data = json.loads(EXAMPLE_FILE.read_text())
        event = DeltaOneAcceptanceEvent(**data)

        # Contract field assertions
        assert event.event_version == "deltaone.acceptance/v1"
        assert isinstance(event.model_id, str) and event.model_id
        assert isinstance(event.model_id_uint, str)
        assert int(event.model_id_uint) >= 0
        assert isinstance(event.eval_id, str) and event.eval_id
        assert isinstance(event.mlflow_run_id, str) and event.mlflow_run_id
        assert isinstance(event.benchmark_spec_id, str) and event.benchmark_spec_id
        assert isinstance(event.primary_metric_name, str) and event.primary_metric_name
        assert isinstance(event.primary_metric_mlflow_name, str)
        assert event.metric_family in SUPPORTED_METRIC_FAMILIES
        assert 0 <= event.baseline_score_bps <= 10000
        assert 0 <= event.candidate_score_bps <= 10000
        assert event.delta_bps == event.candidate_score_bps - event.baseline_score_bps
        assert 0 <= event.delta_threshold_bps <= 10000
        assert event.attestation_hash.startswith("0x")
        assert event.idempotency_key.startswith("0x")
        assert isinstance(event.guardrail_summary, DeltaOneGuardrailSummary)
        assert event.max_cost_usd_micro >= 0
        assert event.actual_cost_usd_micro >= 0


# ---------------------------------------------------------------------------
# Deterministic JSON serialization
# ---------------------------------------------------------------------------


class TestDeterministicSerialization:
    def test_two_identical_events_produce_identical_json(self) -> None:
        event_a = _valid_event()
        event_b = _valid_event()
        json_a = json.dumps(event_a.model_dump(), sort_keys=True, separators=(",", ":"))
        json_b = json.dumps(event_b.model_dump(), sort_keys=True, separators=(",", ":"))
        assert json_a == json_b

    def test_canonical_sha256_is_deterministic(self) -> None:
        payload = {"a": 1, "b": "x"}
        h1 = canonical_sha256(payload)
        h2 = canonical_sha256(payload)
        assert h1 == h2
        assert h1.startswith("0x")
        assert len(h1) == 66  # 0x + 64 hex
