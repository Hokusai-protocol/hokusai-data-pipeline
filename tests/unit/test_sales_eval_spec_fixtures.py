"""Unit tests for sales outreach EvalSpec fixtures.

Validates that all five policy-backed fixtures:
- Parse against the EvalSpec schema without errors.
- Encode the expected measurement_policy.type and mint_eligible values.
- Use revenue_per_1000_messages only with eligible measurement policies.
- Distinguish diagnostic-only logging from mint-eligible revenue metrics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.api.schemas.benchmark_spec import EvalSpec

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "schema" / "examples"

MINT_ELIGIBLE_POLICIES = {
    "online_ab",
    "reward_model",
    "off_policy",
    "exact_observed_output",
}

FIXTURE_POLICY_MAP: dict[str, tuple[str, bool]] = {
    # filename_stem -> (expected_policy_type, expected_mint_eligible)
    "sales_eval_spec.online_ab.v1": ("online_ab", True),
    "sales_eval_spec.reward_model.v1": ("reward_model", True),
    "sales_eval_spec.off_policy.v1": ("off_policy", True),
    "sales_eval_spec.exact_observed.v1": ("exact_observed_output", True),
    "sales_eval_spec.diagnostic_only.v1": ("diagnostic_only", False),
}

ALL_FIXTURE_FILENAMES = [f"{stem}.json" for stem in FIXTURE_POLICY_MAP]

MINT_ELIGIBLE_FIXTURE_FILENAMES = [
    f"{stem}.json" for stem, (_, eligible) in FIXTURE_POLICY_MAP.items() if eligible
]

REQUIRED_EVAL_SPEC_FIELDS = {
    "primary_metric",
    "secondary_metrics",
    "guardrails",
    "measurement_policy",
    "label_policy",
    "coverage_policy",
    "min_examples",
    "metric_family",
}


def _load_fixture(filename: str) -> dict:
    path = EXAMPLES_DIR / filename
    assert path.exists(), f"Fixture not found: {path}"
    return json.loads(path.read_text())


def _policy_type(data: dict) -> str:
    return data["measurement_policy"]["type"]


@pytest.mark.parametrize("filename", ALL_FIXTURE_FILENAMES)
class TestAllFixturesValidateSchema:
    def test_validates_against_eval_spec(self, filename: str) -> None:
        data = _load_fixture(filename)
        spec = EvalSpec.model_validate(data)
        assert spec.primary_metric is not None

    def test_required_top_level_fields_present(self, filename: str) -> None:
        data = _load_fixture(filename)
        missing = REQUIRED_EVAL_SPEC_FIELDS - data.keys()
        assert not missing, f"{filename} is missing fields: {missing}"

    def test_measurement_policy_has_type(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert (
            "type" in data["measurement_policy"]
        ), f"{filename}: measurement_policy must include a 'type' field"

    def test_measurement_policy_has_mint_eligible(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert (
            "mint_eligible" in data["measurement_policy"]
        ), f"{filename}: measurement_policy must include a 'mint_eligible' field"

    def test_has_secondary_metrics(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert isinstance(data["secondary_metrics"], list)
        assert (
            len(data["secondary_metrics"]) > 0
        ), f"{filename}: expected at least one secondary metric"

    def test_has_guardrails(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert isinstance(data["guardrails"], list)
        assert len(data["guardrails"]) > 0, f"{filename}: expected at least one guardrail"

    def test_min_examples_positive(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert data["min_examples"] >= 1

    def test_primary_metric_has_name_and_direction(self, filename: str) -> None:
        data = _load_fixture(filename)
        pm = data["primary_metric"]
        assert "name" in pm
        assert pm["direction"] in ("higher_is_better", "lower_is_better")


class TestDiagnosticOnlyFixture:
    def test_is_not_mint_eligible(self) -> None:
        data = _load_fixture("sales_eval_spec.diagnostic_only.v1.json")
        assert data["measurement_policy"]["mint_eligible"] is False

    def test_policy_type_is_diagnostic_only(self) -> None:
        data = _load_fixture("sales_eval_spec.diagnostic_only.v1.json")
        assert _policy_type(data) == "diagnostic_only"

    def test_primary_metric_is_not_revenue(self) -> None:
        data = _load_fixture("sales_eval_spec.diagnostic_only.v1.json")
        assert data["primary_metric"]["name"] != "revenue_per_1000_messages"

    def test_has_secondary_metrics_for_logging(self) -> None:
        data = _load_fixture("sales_eval_spec.diagnostic_only.v1.json")
        assert len(data["secondary_metrics"]) > 0

    def test_has_guardrails(self) -> None:
        data = _load_fixture("sales_eval_spec.diagnostic_only.v1.json")
        assert len(data["guardrails"]) > 0

    def test_metric_family_is_not_zero_inflated_continuous(self) -> None:
        data = _load_fixture("sales_eval_spec.diagnostic_only.v1.json")
        assert data["metric_family"] != "zero_inflated_continuous"

    def test_validates_against_eval_spec(self) -> None:
        data = _load_fixture("sales_eval_spec.diagnostic_only.v1.json")
        spec = EvalSpec.model_validate(data)
        assert spec.primary_metric.name != "revenue_per_1000_messages"
        assert spec.measurement_policy is not None
        assert spec.measurement_policy["mint_eligible"] is False


@pytest.mark.parametrize("filename", MINT_ELIGIBLE_FIXTURE_FILENAMES)
class TestRevenueMetricRequiresEligiblePolicy:
    def test_primary_metric_is_revenue_per_1000(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert data["primary_metric"]["name"] == "revenue_per_1000_messages"

    def test_policy_type_is_mint_eligible(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert _policy_type(data) in MINT_ELIGIBLE_POLICIES

    def test_mint_eligible_is_true(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert data["measurement_policy"]["mint_eligible"] is True

    def test_metric_family_is_zero_inflated_continuous(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert data["metric_family"] == "zero_inflated_continuous"

    def test_primary_metric_unit_is_usd(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert data["primary_metric"]["unit"] == "usd_per_1000_messages"

    def test_unit_of_analysis_is_prospect_message(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert data["unit_of_analysis"] == "prospect_message"

    def test_min_examples_meets_floor(self, filename: str) -> None:
        data = _load_fixture(filename)
        assert data["min_examples"] >= 1000


class TestFixtureInventory:
    def test_all_five_fixtures_exist(self) -> None:
        for filename in ALL_FIXTURE_FILENAMES:
            path = EXAMPLES_DIR / filename
            assert path.exists(), f"Missing fixture: {filename}"

    def test_policy_types_cover_required_set(self) -> None:
        observed_types = set()
        for filename in ALL_FIXTURE_FILENAMES:
            data = _load_fixture(filename)
            observed_types.add(_policy_type(data))
        expected = MINT_ELIGIBLE_POLICIES | {"diagnostic_only"}
        assert observed_types == expected

    def test_exactly_four_mint_eligible_fixtures(self) -> None:
        eligible_count = 0
        for filename in ALL_FIXTURE_FILENAMES:
            data = _load_fixture(filename)
            if data["measurement_policy"]["mint_eligible"]:
                eligible_count += 1
        assert eligible_count == 4

    def test_exactly_one_diagnostic_only_fixture(self) -> None:
        diagnostic_count = 0
        for filename in ALL_FIXTURE_FILENAMES:
            data = _load_fixture(filename)
            if _policy_type(data) == "diagnostic_only":
                diagnostic_count += 1
        assert diagnostic_count == 1
