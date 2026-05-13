"""Contract tests for the sales custom outcome eval metric definitions.

Tests verify:
1. Metric inventory — SALES_METRICS keys, attribute completeness, mlflow_name derivation.
2. Scorer registry alignment — every scorer_ref resolves in the registry.
3. Measurement policy split — mint-eligible vs diagnostic-only policy sets.
4. JSON schema validation — valid examples pass, invalid examples fail.
5. Denominator rules — all four cases are covered and non-empty.
6. Existing eval spec fixture cross-validation — known metric names in fixtures map
   to canonical contract names.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import src.evaluation.scorers.builtin  # noqa: F401  — register scorers as side effect
from src.evaluation.sales_metrics import (
    DIAGNOSTIC_ONLY_POLICIES,
    MEASUREMENT_POLICIES,
    MINT_ELIGIBLE_POLICIES,
    SALES_METRIC_NAMES,
    SALES_METRICS,
    SALES_OUTCOME_ROW_SCHEMA_VERSION,
    SalesMetricContract,
)
from src.evaluation.scorers.registry import resolve_scorer
from src.utils.metric_naming import derive_mlflow_name

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"
EXAMPLES_DIR = SCHEMA_DIR / "examples"

_VALID_EXAMPLE_FILES = [
    "sales_outcome_row.qualified_meeting.v1.json",
    "sales_outcome_row.lead_scoring_qualified.v1.json",
    "sales_outcome_row.lead_scoring_unqualified.v1.json",
    "sales_outcome_row.revenue.v1.json",
    "sales_outcome_row.spam_complaint.v1.json",
    "sales_outcome_row.unsubscribe.v1.json",
]

_INVALID_EXAMPLE_FILES = [
    "sales_outcome_row.invalid_negative_count.v1.json",
]

_EVAL_SPEC_FIXTURE_STEMS = [
    "sales_eval_spec.online_ab.v1",
    "sales_eval_spec.reward_model.v1",
    "sales_eval_spec.off_policy.v1",
    "sales_eval_spec.exact_observed.v1",
    "sales_eval_spec.diagnostic_only.v1",
    "sales_eval_spec.lead_scoring.v1",
]

# Unprefixed names used in existing eval spec fixtures that map to canonical sales:* names.
_FIXTURE_NAME_TO_CANONICAL: dict[str, str] = {
    "revenue_per_1000_messages": "sales:revenue_per_1000_messages",
    "unsubscribe_rate": "sales:unsubscribe_rate",
    "spam_complaint_rate": "sales:spam_complaint_rate",
    "qualified_meeting_rate": "sales:qualified_meeting_rate",
}

# Names in existing fixtures that are NOT sales contract metrics and should be ignored.
_NON_CONTRACT_METRIC_NAMES = frozenset(
    {
        "reply_rate",
        "message_quality_score",
        "conversion_rate",
        "personalization_score",
        "meeting_booked_rate",
        "tone_appropriateness",
    }
)


@pytest.fixture(scope="module")
def row_schema() -> dict:
    return json.loads((SCHEMA_DIR / "sales_outcome_row.v1.json").read_text())


@pytest.fixture(scope="module")
def row_validator(row_schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(row_schema)
    return Draft202012Validator(row_schema)


# ---------------------------------------------------------------------------
# 1. Metric inventory
# ---------------------------------------------------------------------------


class TestMetricInventory:
    def test_sales_metric_names_contains_all_four(self) -> None:
        assert set(SALES_METRIC_NAMES) == {
            "sales:qualified_meeting_rate",
            "sales:revenue_per_1000_messages",
            "sales:spam_complaint_rate",
            "sales:unsubscribe_rate",
        }

    def test_sales_metrics_keys_match_names(self) -> None:
        assert set(SALES_METRICS.keys()) == set(SALES_METRIC_NAMES)

    def test_all_contracts_are_sales_metric_contract_instances(self) -> None:
        for name, contract in SALES_METRICS.items():
            assert isinstance(contract, SalesMetricContract), f"{name} is not a SalesMetricContract"

    def test_hokusai_names_match_dict_keys(self) -> None:
        for key, contract in SALES_METRICS.items():
            assert contract.hokusai_name == key

    def test_mlflow_names_derived_from_hokusai_names(self) -> None:
        for name, contract in SALES_METRICS.items():
            assert contract.mlflow_name == derive_mlflow_name(name), f"{name}: mlflow_name mismatch"

    def test_derived_mlflow_names_are_unique(self) -> None:
        mlflow_names = [c.mlflow_name for c in SALES_METRICS.values()]
        assert len(mlflow_names) == len(set(mlflow_names))

    def test_all_contracts_have_nonempty_required_string_fields(self) -> None:
        required_str_fields = [
            "hokusai_name",
            "mlflow_name",
            "direction",
            "metric_family",
            "comparator",
            "aggregation",
            "threshold_semantics",
            "unit_of_analysis",
            "scorer_ref",
            "unit",
        ]
        for name, contract in SALES_METRICS.items():
            for field in required_str_fields:
                value = getattr(contract, field)
                assert value, f"{name}.{field} must be non-empty"

    def test_all_contracts_have_nonempty_hem_tags(self) -> None:
        for name, contract in SALES_METRICS.items():
            assert contract.hem_tags, f"{name}.hem_tags must be non-empty"

    def test_all_contracts_have_nonempty_deltaone_tags(self) -> None:
        for name, contract in SALES_METRICS.items():
            assert contract.deltaone_tags, f"{name}.deltaone_tags must be non-empty"

    def test_directions_are_valid(self) -> None:
        valid_directions = {"higher_is_better", "lower_is_better"}
        for name, contract in SALES_METRICS.items():
            assert contract.direction in valid_directions, f"{name} has invalid direction"

    def test_qualified_meeting_rate_direction(self) -> None:
        assert SALES_METRICS["sales:qualified_meeting_rate"].direction == "higher_is_better"

    def test_revenue_direction(self) -> None:
        assert SALES_METRICS["sales:revenue_per_1000_messages"].direction == "higher_is_better"

    def test_spam_complaint_rate_direction(self) -> None:
        assert SALES_METRICS["sales:spam_complaint_rate"].direction == "lower_is_better"

    def test_unsubscribe_rate_direction(self) -> None:
        assert SALES_METRICS["sales:unsubscribe_rate"].direction == "lower_is_better"

    def test_revenue_uses_zero_inflated_continuous_comparator(self) -> None:
        contract = SALES_METRICS["sales:revenue_per_1000_messages"]
        assert contract.comparator == "zero_inflated_continuous"

    def test_rate_metrics_use_proportion_comparator(self) -> None:
        for name in [
            "sales:qualified_meeting_rate",
            "sales:spam_complaint_rate",
            "sales:unsubscribe_rate",
        ]:
            assert (
                SALES_METRICS[name].comparator == "proportion"
            ), f"{name} should use proportion comparator"

    def test_revenue_aggregation_is_mean_per_n(self) -> None:
        assert SALES_METRICS["sales:revenue_per_1000_messages"].aggregation == "MEAN_PER_N"

    def test_rate_metrics_aggregation_is_mean(self) -> None:
        for name in [
            "sales:qualified_meeting_rate",
            "sales:spam_complaint_rate",
            "sales:unsubscribe_rate",
        ]:
            assert SALES_METRICS[name].aggregation == "MEAN", f"{name} should use MEAN aggregation"

    def test_schema_version_sentinel(self) -> None:
        assert SALES_OUTCOME_ROW_SCHEMA_VERSION == "sales_outcome_row/v1"


# ---------------------------------------------------------------------------
# 2. Scorer registry alignment
# ---------------------------------------------------------------------------


class TestScorerRegistryAlignment:
    def test_all_scorer_refs_resolve(self) -> None:
        for _name, contract in SALES_METRICS.items():
            scorer = resolve_scorer(contract.scorer_ref)
            assert scorer is not None, f"scorer_ref {contract.scorer_ref!r} did not resolve"

    def test_scorer_ref_equals_hokusai_name(self) -> None:
        for name, contract in SALES_METRICS.items():
            assert contract.scorer_ref == name, f"{name}: scorer_ref should equal hokusai_name"

    def test_resolved_scorers_have_expected_output_metric_keys(self) -> None:
        for name, contract in SALES_METRICS.items():
            scorer = resolve_scorer(contract.scorer_ref)
            assert (
                name in scorer.metadata.output_metric_keys
            ), f"scorer for {name} does not output the canonical metric key"


# ---------------------------------------------------------------------------
# 3. Measurement policy split
# ---------------------------------------------------------------------------


class TestMeasurementPolicySplit:
    def test_all_five_policies_present(self) -> None:
        assert MEASUREMENT_POLICIES == {
            "online_ab",
            "reward_model",
            "off_policy",
            "exact_observed_output",
            "diagnostic_only",
        }

    def test_mint_eligible_policies_are_exactly_four(self) -> None:
        assert MINT_ELIGIBLE_POLICIES == {
            "online_ab",
            "reward_model",
            "off_policy",
            "exact_observed_output",
        }

    def test_diagnostic_only_policies_contains_diagnostic_only(self) -> None:
        assert DIAGNOSTIC_ONLY_POLICIES == {"diagnostic_only"}

    def test_diagnostic_only_not_in_mint_eligible(self) -> None:
        assert "diagnostic_only" not in MINT_ELIGIBLE_POLICIES

    def test_mint_eligible_and_diagnostic_only_are_disjoint(self) -> None:
        assert MINT_ELIGIBLE_POLICIES.isdisjoint(DIAGNOSTIC_ONLY_POLICIES)

    def test_all_policies_accounted_for(self) -> None:
        assert MINT_ELIGIBLE_POLICIES | DIAGNOSTIC_ONLY_POLICIES == MEASUREMENT_POLICIES

    def test_exact_observed_output_is_canonical_not_exact_observed(self) -> None:
        assert "exact_observed_output" in MINT_ELIGIBLE_POLICIES
        assert "exact_observed" not in MEASUREMENT_POLICIES


# ---------------------------------------------------------------------------
# 4. JSON schema validation
# ---------------------------------------------------------------------------


class TestJsonSchemaValidation:
    def test_schema_is_valid_draft_2020_12(self, row_schema: dict) -> None:
        Draft202012Validator.check_schema(row_schema)

    def test_schema_version_sentinel_in_schema(self, row_schema: dict) -> None:
        assert row_schema["properties"]["schema_version"]["const"] == "sales_outcome_row/v1"

    @pytest.mark.parametrize("filename", _VALID_EXAMPLE_FILES)
    def test_valid_examples_pass(self, row_validator: Draft202012Validator, filename: str) -> None:
        data = json.loads((EXAMPLES_DIR / filename).read_text())
        errors = list(row_validator.iter_errors(data))
        assert not errors, f"{filename} should be valid but got: {[e.message for e in errors]}"

    @pytest.mark.parametrize("filename", _INVALID_EXAMPLE_FILES)
    def test_invalid_examples_fail(
        self, row_validator: Draft202012Validator, filename: str
    ) -> None:
        data = json.loads((EXAMPLES_DIR / filename).read_text())
        errors = list(row_validator.iter_errors(data))
        assert errors, f"{filename} should be invalid but passed validation"

    def test_invalid_negative_numerator_fails(self, row_validator: Draft202012Validator) -> None:
        invalid = EXAMPLES_DIR / "sales_outcome_row.invalid_negative_count.v1.json"
        data = json.loads(invalid.read_text())
        errors = list(row_validator.iter_errors(data))
        assert any(
            "minimum" in e.message or "-1" in e.message for e in errors
        ), "Expected a minimum constraint violation for negative numerator"

    def test_missing_metric_name_fails(self, row_validator: Draft202012Validator) -> None:
        row = {
            "schema_version": "sales_outcome_row/v1",
            "row_id": "test-001",
            "benchmark_spec_id": "bspec-001",
            "eval_id": "eval-001",
            "model_id": "model-001",
            "campaign_id": "camp-001",
            "unit_id": "unit-001",
            "unit_of_analysis": "prospect_message",
            "measurement_policy": "online_ab",
            "scorer_ref": "sales:spam_complaint_rate",
            "message_count": 1,
            "delivered_count": 1,
            "numerator": 0,
            "denominator": 1,
            "observed_at": "2024-11-01T00:00:00Z",
            "label_status": "observed",
        }
        errors = list(row_validator.iter_errors(row))
        assert errors, "Row missing metric_name should fail"
        assert any(
            "metric_name" in e.message or "'metric_name' is a required" in e.message for e in errors
        )

    def test_unknown_metric_name_fails(self, row_validator: Draft202012Validator) -> None:
        row = {
            "schema_version": "sales_outcome_row/v1",
            "row_id": "test-002",
            "benchmark_spec_id": "bspec-001",
            "eval_id": "eval-001",
            "model_id": "model-001",
            "campaign_id": "camp-001",
            "unit_id": "unit-001",
            "unit_of_analysis": "prospect_message",
            "measurement_policy": "online_ab",
            "metric_name": "sales:reply_rate",
            "scorer_ref": "sales:reply_rate",
            "message_count": 1,
            "delivered_count": 1,
            "numerator": 0,
            "denominator": 1,
            "observed_at": "2024-11-01T00:00:00Z",
            "label_status": "observed",
        }
        errors = list(row_validator.iter_errors(row))
        assert errors, "Row with unknown metric_name 'sales:reply_rate' should fail"

    def test_exact_observed_alias_fails(self, row_validator: Draft202012Validator) -> None:
        """'exact_observed' must be rejected; only 'exact_observed_output' is canonical."""
        row = {
            "schema_version": "sales_outcome_row/v1",
            "row_id": "test-003",
            "benchmark_spec_id": "bspec-001",
            "eval_id": "eval-001",
            "model_id": "model-001",
            "campaign_id": "camp-001",
            "unit_id": "unit-001",
            "unit_of_analysis": "prospect_message",
            "measurement_policy": "exact_observed",
            "metric_name": "sales:revenue_per_1000_messages",
            "scorer_ref": "sales:revenue_per_1000_messages",
            "message_count": 1,
            "delivered_count": 1,
            "numerator": 1000.0,
            "denominator": 1000,
            "observed_at": "2024-11-01T00:00:00Z",
            "label_status": "observed",
        }
        errors = list(row_validator.iter_errors(row))
        assert errors, (
            "Row with measurement_policy='exact_observed' should fail; "
            "only 'exact_observed_output' is canonical"
        )

    def test_extra_top_level_property_fails(self, row_validator: Draft202012Validator) -> None:
        data = json.loads((EXAMPLES_DIR / "sales_outcome_row.spam_complaint.v1.json").read_text())
        data["unknown_extra_field"] = "this should not be allowed"
        errors = list(row_validator.iter_errors(data))
        assert errors, "Row with extra top-level property should fail (additionalProperties: false)"

    def test_coverage_fraction_above_one_fails(self, row_validator: Draft202012Validator) -> None:
        data = json.loads((EXAMPLES_DIR / "sales_outcome_row.spam_complaint.v1.json").read_text())
        data["coverage_fraction"] = 1.5
        errors = list(row_validator.iter_errors(data))
        assert errors, "coverage_fraction > 1.0 should fail"

    def test_coverage_fraction_below_zero_fails(self, row_validator: Draft202012Validator) -> None:
        data = json.loads((EXAMPLES_DIR / "sales_outcome_row.spam_complaint.v1.json").read_text())
        data["coverage_fraction"] = -0.1
        errors = list(row_validator.iter_errors(data))
        assert errors, "coverage_fraction < 0.0 should fail"

    def test_invalid_revenue_currency_pattern_fails(
        self, row_validator: Draft202012Validator
    ) -> None:
        data = json.loads((EXAMPLES_DIR / "sales_outcome_row.revenue.v1.json").read_text())
        data["revenue_currency"] = "usd"
        errors = list(row_validator.iter_errors(data))
        assert errors, "Lowercase currency 'usd' should fail (must be [A-Z]{3})"

    def test_wrong_schema_version_fails(self, row_validator: Draft202012Validator) -> None:
        data = json.loads((EXAMPLES_DIR / "sales_outcome_row.revenue.v1.json").read_text())
        data["schema_version"] = "sales_outcome_row/v2"
        errors = list(row_validator.iter_errors(data))
        assert errors, "Wrong schema_version should fail the const constraint"


# ---------------------------------------------------------------------------
# 5. Denominator rules
# ---------------------------------------------------------------------------


class TestDenominatorRules:
    _REQUIRED_CASES = {"zero_messages", "missing_label", "delayed_label", "partial_coverage"}

    def test_all_metrics_have_all_four_denominator_cases(self) -> None:
        for name, contract in SALES_METRICS.items():
            missing = self._REQUIRED_CASES - set(contract.denominator_rules.keys())
            assert not missing, f"{name} is missing denominator cases: {missing}"

    def test_all_denominator_rules_are_nonempty(self) -> None:
        for name, contract in SALES_METRICS.items():
            for case, rule in contract.denominator_rules.items():
                assert (
                    rule and rule.strip()
                ), f"{name}.denominator_rules[{case!r}] must be non-empty"


# ---------------------------------------------------------------------------
# 6. Existing eval spec fixture cross-validation
# ---------------------------------------------------------------------------


class TestEvalSpecFixtureCrossValidation:
    def _load_fixture(self, stem: str) -> dict:
        path = EXAMPLES_DIR / f"{stem}.json"
        assert path.exists(), f"Eval spec fixture not found: {path}"
        return json.loads(path.read_text())

    def _normalize_metric_name(self, name: str) -> str | None:
        """Map an unprefixed fixture name to its canonical sales:* name, or None."""
        if name in SALES_METRICS:
            return name
        canonical = _FIXTURE_NAME_TO_CANONICAL.get(name)
        return canonical

    @pytest.mark.parametrize("stem", _EVAL_SPEC_FIXTURE_STEMS)
    def test_primary_metric_maps_to_known_name(self, stem: str) -> None:
        data = self._load_fixture(stem)
        primary_name = data["primary_metric"]["name"]
        canonical = self._normalize_metric_name(primary_name)
        if canonical is not None:
            assert canonical in SALES_METRICS, (
                f"{stem}: primary metric {primary_name!r} maps to {canonical!r} "
                "but that is not in SALES_METRICS"
            )

    @pytest.mark.parametrize("stem", _EVAL_SPEC_FIXTURE_STEMS)
    def test_guardrail_names_map_to_known_or_ignored_names(self, stem: str) -> None:
        data = self._load_fixture(stem)
        for guardrail in data.get("guardrails", []):
            name = guardrail["name"]
            canonical = self._normalize_metric_name(name)
            if name not in _NON_CONTRACT_METRIC_NAMES and canonical is not None:
                assert canonical in SALES_METRICS, (
                    f"{stem}: guardrail {name!r} maps to {canonical!r} "
                    "but that is not in SALES_METRICS"
                )

    def test_revenue_fixtures_use_zero_inflated_continuous_family(self) -> None:
        revenue_fixtures = [
            stem for stem in _EVAL_SPEC_FIXTURE_STEMS if "diagnostic_only" not in stem
        ]
        for stem in revenue_fixtures:
            data = self._load_fixture(stem)
            primary_name = data["primary_metric"]["name"]
            canonical = self._normalize_metric_name(primary_name)
            if canonical == "sales:revenue_per_1000_messages":
                assert (
                    data["metric_family"] == "zero_inflated_continuous"
                ), f"{stem}: revenue primary metric should use zero_inflated_continuous family"

    def test_contract_revenue_metric_family_matches_fixture_convention(self) -> None:
        contract = SALES_METRICS["sales:revenue_per_1000_messages"]
        assert contract.metric_family == "zero_inflated_continuous"
